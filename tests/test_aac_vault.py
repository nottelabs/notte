import asyncio
import json
import shutil
import stat
import subprocess
import threading
from _thread import LockType
from pathlib import Path
from types import TracebackType
from typing import cast

import pyotp
import pytest
from notte_core.credentials.aac import AacVault

SEED = "JBSWY3DPEHPK3PXP"  # pragma: allowlist secret
GITHUB_CREDENTIAL = {
    "username": "octocat",
    "password": "gh-secret-123",  # pragma: allowlist secret
    "totp": SEED,
    "uri": "https://github.com",
    "notes": None,
}
# a credential payload as `aac` could print it, including malformed ones
Payload = dict[str, str | None] | list[str] | str | None
CONNECTION_FAILED = {"error": {"code": "connection_failed", "message": "connection failed"}, "success": False}


class FakeAac:
    """An `aac` executable that prints `stdout`, exits with `exit_code` and records each call's arguments, $HOME and $AAC_TOKEN."""

    def __init__(self, tmp_path: Path, stdout: str, exit_code: int = 0, delay: float = 0, pairs: bool = True) -> None:
        self.path: Path = tmp_path / "aac"
        self.calls_file: Path = tmp_path / "calls.jsonl"
        output_file = tmp_path / "stdout.txt"
        _ = output_file.write_text(stdout)
        _ = self.path.write_text(
            "#!/usr/bin/env python3\n"
            "import json, os, sys, time\n"
            f"with open({str(self.calls_file)!r}, 'a') as f:\n"
            "    f.write(json.dumps({'args': sys.argv[1:], 'home': os.environ.get('HOME'), 'token': os.environ.get('AAC_TOKEN')}) + '\\n')\n"
            # like `aac`, save the paired connection under $HOME before answering the credential request
            f"if {pairs} and os.environ.get('AAC_TOKEN'):\n"
            "    cache = os.path.join(os.environ['HOME'], '.access-protocol')\n"
            "    os.makedirs(cache, exist_ok=True)\n"
            "    with open(os.path.join(cache, 'connection_cache_remote_client.json'), 'w') as f:\n"
            "        json.dump({'connections': [{'remote_fingerprint': 'ab' * 32}]}, f)\n"
            f"time.sleep({delay})\n"
            f"sys.stdout.write(open({str(output_file)!r}).read())\n"
            f"sys.exit({exit_code})\n"
        )
        self.path.chmod(self.path.stat().st_mode | stat.S_IXUSR)

    def _records(self) -> list[dict[str, list[str] | str | None]]:
        if not self.calls_file.exists():
            return []
        return [json.loads(line) for line in self.calls_file.read_text().splitlines()]

    @property
    def calls(self) -> list[list[str]]:
        return [record["args"] for record in self._records()]  # pyright: ignore[reportReturnType]

    @property
    def homes(self) -> list[str]:
        return [record["home"] for record in self._records()]  # pyright: ignore[reportReturnType]

    @property
    def tokens(self) -> list[str | None]:
        return [record["token"] for record in self._records()]  # pyright: ignore[reportReturnType]


def _credential_response(credential: Payload) -> str:
    return json.dumps({"credential": credential, "domain": "github.com", "success": True})


def _flag(args: list[str], name: str) -> str | None:
    return args[args.index(name) + 1] if name in args else None


@pytest.fixture()
def fake_aac(tmp_path: Path) -> FakeAac:
    return FakeAac(tmp_path, _credential_response(GITHUB_CREDENTIAL))


@pytest.fixture()
def vault(fake_aac: FakeAac):
    with AacVault(token="ABC-DEF-123", aac_path=str(fake_aac.path)) as v:
        yield v


@pytest.fixture(autouse=True)
def no_env_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AAC_TOKEN", raising=False)


class TestAacVaultGetCredentials:
    @pytest.mark.parametrize("credential", [GITHUB_CREDENTIAL, None, {"username": "no-password"}])
    def test_presence_requests_the_domain(self, tmp_path: Path, credential: Payload) -> None:
        fake = FakeAac(tmp_path, _credential_response(credential))
        with AacVault(aac_path=str(fake.path)) as vault:
            assert vault.has_credential("https://gist.github.com/login") is (credential == GITHUB_CREDENTIAL)
        assert _flag(fake.calls[0], "--domain") == "github.com"

    def test_fetches_credential_by_root_domain(self, vault: AacVault, fake_aac: FakeAac) -> None:
        creds = asyncio.run(vault.get_credentials_async("https://gist.github.com/login"))
        assert creds is not None
        assert creds["password"] == "gh-secret-123"  # pragma: allowlist secret
        assert creds["username"] == "octocat"

        [args] = fake_aac.calls
        assert args[0] == "connect"
        assert _flag(args, "--domain") == "github.com"
        assert _flag(args, "--output") == "json"
        assert _flag(args, "--proxy-url") == "wss://ap.lesspassword.dev"
        assert _flag(args, "--timeout") == "120"

    def test_turns_the_totp_seed_into_a_code(self, vault: AacVault) -> None:
        creds = asyncio.run(vault.get_credentials_async("https://github.com"))
        assert creds is not None
        assert creds["mfa_secret"] != SEED
        assert pyotp.TOTP(SEED).verify(creds["mfa_secret"], valid_window=1)

    def test_applies_the_settings_of_an_otpauth_uri(self, tmp_path: Path) -> None:
        uri = f"otpauth://totp/GitHub:octocat?secret={SEED}&issuer=GitHub&digits=8&period=60&algorithm=SHA256"
        fake = FakeAac(tmp_path, _credential_response({**GITHUB_CREDENTIAL, "totp": uri}))
        with AacVault(token="ABC-DEF-123", aac_path=str(fake.path)) as vault:
            creds = asyncio.run(vault.get_credentials_async("https://github.com"))
        assert creds is not None
        assert len(creds["mfa_secret"]) == 8
        assert pyotp.parse_uri(uri).verify(creds["mfa_secret"], valid_window=1)

    @pytest.mark.parametrize("code", ["123456", "234567", "01234567", "23456723"])
    def test_preserves_generated_codes_and_tracks_them_for_masking(self, tmp_path: Path, code: str) -> None:
        fake = FakeAac(tmp_path, _credential_response({**GITHUB_CREDENTIAL, "totp": code}))
        with AacVault(token="ABC-DEF-123", aac_path=str(fake.path)) as vault:
            creds = vault.get_credentials("https://github.com")
            assert creds is not None and creds["password"] == GITHUB_CREDENTIAL["password"]
            assert creds["mfa_secret"] == code
            assert vault.get_replacement_map()[code] == "999779"

    @pytest.mark.parametrize("seed", ["2345672345672345", "23456723456723452345672345672345"])
    def test_numeric_seeds_require_an_otpauth_uri(self, tmp_path: Path, seed: str) -> None:
        fake = FakeAac(tmp_path, _credential_response({**GITHUB_CREDENTIAL, "totp": seed}))
        with AacVault(aac_path=str(fake.path)) as vault:
            with pytest.raises(ValueError, match="otpauth URI") as error:
                _ = vault.get_credentials("https://github.com")
            assert seed not in str(error.value)
            assert vault.past_credentials() == {}

    @pytest.mark.parametrize("seed", ["23456723", "2345672345672345"])
    def test_numeric_seeds_in_uris_generate_codes(self, tmp_path: Path, seed: str) -> None:
        uri = f"otpauth://totp/GitHub?secret={seed}"
        fake = FakeAac(tmp_path, _credential_response({**GITHUB_CREDENTIAL, "totp": uri}))
        with AacVault(aac_path=str(fake.path)) as vault:
            creds = vault.get_credentials("https://github.com")
        assert creds is not None
        assert creds["mfa_secret"] != seed
        assert pyotp.parse_uri(uri).verify(creds["mfa_secret"], valid_window=1)

    def test_tracks_credentials_for_screenshot_masking(self, vault: AacVault) -> None:
        _ = asyncio.run(vault.get_credentials_async("https://github.com"))
        assert list(vault.past_credentials()) == ["https://github.com"]

    def test_omits_missing_username_and_totp(self, tmp_path: Path) -> None:
        credential = {
            "username": None,
            "password": "pass",  # pragma: allowlist secret
            "totp": None,
            "uri": None,
            "notes": None,
        }
        fake = FakeAac(tmp_path, _credential_response(credential))
        with AacVault(token="ABC-DEF-123", aac_path=str(fake.path)) as vault:
            creds = asyncio.run(vault.get_credentials_async("https://example.com"))
        assert creds == {"password": "pass"}  # pragma: allowlist secret

    def test_returns_none_on_failure(self, tmp_path: Path) -> None:
        fake = FakeAac(tmp_path, json.dumps(CONNECTION_FAILED), exit_code=2)
        with AacVault(aac_path=str(fake.path)) as vault:
            assert asyncio.run(vault.get_credentials_async("https://github.com")) is None

    @pytest.mark.parametrize("credential", [None, "not-an-object", ["password"], {"username": "no-password"}])
    def test_returns_none_for_an_unusable_credential(self, tmp_path: Path, credential: Payload) -> None:
        fake = FakeAac(tmp_path, _credential_response(credential))
        with AacVault(aac_path=str(fake.path)) as vault:
            assert asyncio.run(vault.get_credentials_async("https://github.com")) is None

    def test_returns_none_for_output_that_is_not_json(self, tmp_path: Path) -> None:
        fake = FakeAac(tmp_path, "username: octocat\npassword: gh-secret-123\n")  # pragma: allowlist secret
        with AacVault(aac_path=str(fake.path)) as vault:
            assert asyncio.run(vault.get_credentials_async("https://github.com")) is None

    def test_returns_none_on_timeout(self, vault: AacVault, monkeypatch: pytest.MonkeyPatch) -> None:
        def timeout(
            cmd: list[str], *, capture_output: bool, text: bool, timeout: int, check: bool, env: dict[str, str] | None
        ) -> None:
            raise subprocess.TimeoutExpired(cmd, timeout)

        monkeypatch.setattr(subprocess, "run", timeout)
        assert asyncio.run(vault.get_credentials_async("https://github.com")) is None


class TestAacVaultPairing:
    def test_pairs_with_the_token_on_the_first_request_only(self, vault: AacVault, fake_aac: FakeAac) -> None:
        _ = asyncio.run(vault.get_credentials_async("https://github.com"))
        _ = asyncio.run(vault.get_credentials_async("https://github.com"))

        # through the environment: the command line of a process is visible to other local users
        assert fake_aac.tokens == ["ABC-DEF-123", None]
        assert all("ABC-DEF-123" not in args and "--token" not in args for args in fake_aac.calls)
        assert vault.token is None

    def test_does_not_pass_an_inherited_token_after_pairing(
        self, fake_aac: FakeAac, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("AAC_TOKEN", "ENV-TOK-123")
        with AacVault(aac_path=str(fake_aac.path)) as vault:
            _ = vault.get_credentials("https://github.com")
            _ = vault.get_credentials("https://github.com")
        assert fake_aac.tokens == ["ENV-TOK-123", None]

    def test_concurrent_first_requests_pair_once(self, tmp_path: Path) -> None:
        fake = FakeAac(tmp_path, _credential_response(GITHUB_CREDENTIAL), delay=0.5)

        async def request_twice(vault: AacVault) -> None:
            _ = await asyncio.gather(
                vault.get_credentials_async("https://github.com"), vault.get_credentials_async("https://github.com")
            )

        with AacVault(token="ABC-DEF-123", aac_path=str(fake.path)) as vault:
            asyncio.run(request_twice(vault))
        assert fake.tokens == ["ABC-DEF-123", None]
        assert fake.homes[0] == fake.homes[1]

    def test_pairs_in_a_private_home_removed_on_stop(self, fake_aac: FakeAac, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HOME", "/home/user")
        # the session names a connection in the user's cache, which a paired vault does not use
        with AacVault(token="ABC-DEF-123", session="a1b2c3", aac_path=str(fake_aac.path)) as vault:
            _ = vault.get_credentials("https://github.com")
            _ = vault.get_credentials("https://github.com")
            first, second = fake_aac.homes
            assert first == second != "/home/user"
            assert Path(first).is_dir()
            assert "--session" not in fake_aac.calls[1]
        assert not Path(first).exists()

    def test_pairs_again_after_a_restart(self, fake_aac: FakeAac, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HOME", "/home/user")
        vault = AacVault(token="ABC-DEF-123", aac_path=str(fake_aac.path))
        with vault:
            _ = vault.get_credentials("https://github.com")
        with vault:
            assert vault.token == "ABC-DEF-123"
            _ = vault.get_credentials("https://github.com")

        assert fake_aac.tokens == ["ABC-DEF-123", "ABC-DEF-123"]
        assert "/home/user" not in fake_aac.homes
        assert fake_aac.homes[0] != fake_aac.homes[1]

    def test_keeps_the_token_when_pairing_fails(self, tmp_path: Path) -> None:
        fake = FakeAac(tmp_path, json.dumps(CONNECTION_FAILED), exit_code=2, pairs=False)
        with AacVault(token="ABC-DEF-123", aac_path=str(fake.path)) as vault:
            _ = asyncio.run(vault.get_credentials_async("https://github.com"))
            assert vault.token == "ABC-DEF-123"

    @pytest.mark.parametrize(
        "error",
        [
            {"code": "credential_not_found", "message": "not found"},
            {"code": "general_error", "message": "Timeout waiting for credential response"},
        ],
    )
    def test_drops_the_token_when_paired_without_a_credential(self, tmp_path: Path, error: dict[str, str]) -> None:
        fake = FakeAac(tmp_path, json.dumps({"error": error, "success": False}), exit_code=1)
        with AacVault(token="ABC-DEF-123", aac_path=str(fake.path)) as vault:
            assert vault.get_credentials("https://github.com") is None
            assert vault.token is None

    def test_uses_the_session_without_a_token(self, fake_aac: FakeAac, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HOME", "/home/user")
        with AacVault(session="a1b2c3", aac_path=str(fake_aac.path)) as vault:
            _ = asyncio.run(vault.get_credentials_async("https://github.com"))

        [args] = fake_aac.calls
        assert _flag(args, "--session") == "a1b2c3"
        assert fake_aac.tokens == [None]
        assert fake_aac.homes == ["/home/user"]

    def test_reads_token_from_env(self, fake_aac: FakeAac, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AAC_TOKEN", "ENV-TOK-123")
        vault = AacVault(aac_path=str(fake_aac.path))
        assert vault.token == "ENV-TOK-123"


class TestAacVaultLifecycle:
    @pytest.mark.asyncio
    async def test_cancelled_pairing_finishes_before_stop_removes_its_home(
        self, vault: AacVault, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class ObservedLock:
            def __init__(self) -> None:
                self.native: LockType = threading.Lock()
                self.waiting = threading.Event()

            def __enter__(self) -> None:
                if self.native.locked():
                    self.waiting.set()
                _ = self.native.acquire()

            def __exit__(
                self, exc_type: type[BaseException] | None, exc_val: BaseException | None, tb: TracebackType | None
            ) -> None:
                self.native.release()

        lock = ObservedLock()
        vault._lock = cast(LockType, lock)
        started, release, returned = threading.Event(), threading.Event(), threading.Event()
        homes: list[Path] = []

        def pair(
            cmd: list[str], *, capture_output: bool, text: bool, timeout: int, check: bool, env: dict[str, str]
        ) -> subprocess.CompletedProcess[str]:
            home = Path(env["HOME"])
            homes.append(home)
            started.set()
            assert release.wait(5), "pairing was not released"
            cache = home / ".access-protocol" / "connection_cache_remote_client.json"
            cache.parent.mkdir(parents=True, exist_ok=True)
            _ = cache.write_text('{"connections": [{}]}')
            returned.set()
            return subprocess.CompletedProcess(cmd, 0, _credential_response(GITHUB_CREDENTIAL), "")

        monkeypatch.setattr(subprocess, "run", pair)
        request = asyncio.create_task(vault.get_credentials_async("https://github.com"))
        assert await asyncio.to_thread(started.wait, 2)
        _ = request.cancel()
        with pytest.raises(asyncio.CancelledError):
            await request
        closing = asyncio.create_task(asyncio.to_thread(vault.stop))
        try:
            try:
                assert await asyncio.to_thread(lock.waiting.wait, 1), "shutdown did not join the active request"
                assert await asyncio.to_thread(homes[0].is_dir)
            finally:
                release.set()
                await closing
                assert await asyncio.to_thread(returned.wait, 2)
            assert not await asyncio.to_thread(homes[0].exists)
            with pytest.raises(RuntimeError, match="stopped"):
                _ = await vault.get_credentials_async("https://github.com")
        finally:
            await asyncio.to_thread(shutil.rmtree, homes[0], ignore_errors=True)

    def test_start_validates_aac_exists(self) -> None:
        vault = AacVault(token="test", aac_path="/nonexistent/aac")
        with pytest.raises(RuntimeError, match="CLI not found"):
            vault.start()

    def test_start_does_not_call_aac(self, fake_aac: FakeAac) -> None:
        with AacVault(token="ABC-DEF-123", aac_path=str(fake_aac.path)):
            pass
        assert fake_aac.calls == []


class TestAacVaultReadOnly:
    def test_add_credentials_raises(self, vault: AacVault) -> None:
        with pytest.raises(NotImplementedError, match="read-only"):
            vault.add_credentials("https://example.com", password="test")  # pragma: allowlist secret

    def test_delete_credentials_raises(self, vault: AacVault) -> None:
        with pytest.raises(NotImplementedError, match="read-only"):
            vault.delete_credentials("https://example.com")

    def test_list_credentials_returns_empty(self, vault: AacVault) -> None:
        assert vault.list_credentials() == []

    def test_credit_card_not_supported(self, vault: AacVault) -> None:
        with pytest.raises(NotImplementedError):
            vault.set_credit_card(
                card_holder_name="Test", card_number="4242", card_cvv="123", card_full_expiration="12/30"
            )
        with pytest.raises(NotImplementedError):
            _ = vault.get_credit_card()
        with pytest.raises(NotImplementedError):
            vault.delete_credit_card()
