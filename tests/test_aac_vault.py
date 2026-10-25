import asyncio
import json
import stat
import subprocess
from pathlib import Path

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
    """An `aac` executable that prints `stdout`, exits with `exit_code` and records each call's arguments."""

    def __init__(self, tmp_path: Path, stdout: str, exit_code: int = 0) -> None:
        self.path: Path = tmp_path / "aac"
        self.calls_file: Path = tmp_path / "calls.jsonl"
        output_file = tmp_path / "stdout.txt"
        _ = output_file.write_text(stdout)
        _ = self.path.write_text(
            "#!/usr/bin/env python3\n"
            "import json, sys\n"
            f"with open({str(self.calls_file)!r}, 'a') as f:\n"
            "    f.write(json.dumps(sys.argv[1:]) + '\\n')\n"
            f"sys.stdout.write(open({str(output_file)!r}).read())\n"
            f"sys.exit({exit_code})\n"
        )
        self.path.chmod(self.path.stat().st_mode | stat.S_IXUSR)

    @property
    def calls(self) -> list[list[str]]:
        if not self.calls_file.exists():
            return []
        return [json.loads(line) for line in self.calls_file.read_text().splitlines()]


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

    def test_reads_the_seed_of_an_otpauth_uri(self, tmp_path: Path) -> None:
        uri = f"otpauth://totp/GitHub:octocat?secret={SEED}&issuer=GitHub"
        fake = FakeAac(tmp_path, _credential_response({**GITHUB_CREDENTIAL, "totp": uri}))
        with AacVault(token="ABC-DEF-123", aac_path=str(fake.path)) as vault:
            creds = asyncio.run(vault.get_credentials_async("https://github.com"))
        assert creds is not None
        assert pyotp.TOTP(SEED).verify(creds["mfa_secret"], valid_window=1)

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
        def timeout(cmd: list[str], *, capture_output: bool, text: bool, timeout: int, check: bool) -> None:
            raise subprocess.TimeoutExpired(cmd, timeout)

        monkeypatch.setattr(subprocess, "run", timeout)
        assert asyncio.run(vault.get_credentials_async("https://github.com")) is None


class TestAacVaultPairing:
    def test_pairs_with_the_token_on_the_first_request_only(self, vault: AacVault, fake_aac: FakeAac) -> None:
        _ = asyncio.run(vault.get_credentials_async("https://github.com"))
        _ = asyncio.run(vault.get_credentials_async("https://github.com"))

        first, second = fake_aac.calls
        assert _flag(first, "--token") == "ABC-DEF-123"
        assert "--token" not in second
        assert vault.token is None

    def test_keeps_the_token_when_pairing_fails(self, tmp_path: Path) -> None:
        fake = FakeAac(tmp_path, json.dumps(CONNECTION_FAILED), exit_code=2)
        with AacVault(token="ABC-DEF-123", aac_path=str(fake.path)) as vault:
            _ = asyncio.run(vault.get_credentials_async("https://github.com"))
            assert vault.token == "ABC-DEF-123"

    def test_drops_the_token_when_paired_without_a_credential(self, tmp_path: Path) -> None:
        not_found = {"error": {"code": "credential_not_found", "message": "not found"}, "success": False}
        fake = FakeAac(tmp_path, json.dumps(not_found), exit_code=4)
        with AacVault(token="ABC-DEF-123", aac_path=str(fake.path)) as vault:
            assert vault.get_credentials("https://github.com") is None
            assert vault.token is None

    def test_uses_the_session_without_a_token(self, fake_aac: FakeAac) -> None:
        with AacVault(session="a1b2c3", aac_path=str(fake_aac.path)) as vault:
            _ = asyncio.run(vault.get_credentials_async("https://github.com"))

        [args] = fake_aac.calls
        assert _flag(args, "--session") == "a1b2c3"
        assert "--token" not in args

    def test_reads_token_from_env(self, fake_aac: FakeAac, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AAC_TOKEN", "ENV-TOK-123")
        vault = AacVault(aac_path=str(fake_aac.path))
        assert vault.token == "ENV-TOK-123"


class TestAacVaultLifecycle:
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
