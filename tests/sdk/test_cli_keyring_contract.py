"""Contract test: the SDK reads the API keys that notte-cli's own code stores.

The writer in cli_contract/ is compiled into the notte-cli submodule's auth
package, so keys go through the CLI's real keyring code and land in whatever
store it picks on this machine (system store or encrypted file). The SDK must
then find each key. It writes to the machine's credential store, so it only
runs when NOTTE_CLI_CONTRACT=1, which CI sets on disposable runners.

On macOS a Keychain item can only be read without a prompt by the program
that created it. The test therefore creates each item first, readable by any
program, and lets the CLI overwrite it: the CLI writes the service, account
and data, which is the format the SDK depends on, but the access control of
an item the CLI creates itself is not covered.
"""

import json
import os
import secrets
import shutil
import subprocess
import sys
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from notte_sdk import auth

REPO_ROOT = Path(__file__).resolve().parents[2]
CLI_DIR = REPO_ROOT / "notte-cli"
WRITER = Path(__file__).parent / "cli_contract" / "writer_test.go"

pytestmark = pytest.mark.skipif(
    os.getenv("NOTTE_CLI_CONTRACT") != "1",
    reason="writes to the system credential store; set NOTTE_CLI_CONTRACT=1 on a disposable machine",
)

# One API URL per way the SDK maps a URL to a CLI environment label.
API_URLS = [
    "https://api.notte.cc",
    "https://us-staging.notte.cc",
    "http://localhost:8123",
    f"https://contract-{secrets.token_hex(4)}.example.com",
]
STORE_KEYS = [f"{auth.KEYRING_KEY}:{auth.resolve_env_label(url)}" for url in API_URLS] + [auth.KEYRING_KEY]

RunCli = Callable[[list[dict[str, str]]], None]


def _file_value(key: str) -> str | None:
    item = auth._read_file_backend(key)
    return item[0] if item else None


@pytest.fixture(scope="module")
def writer(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Build notte-cli's auth tests with the contract writer added."""
    if shutil.which("go") is None:
        pytest.fail("Go is required to build notte-cli")
    if not (CLI_DIR / "go.mod").is_file():
        pytest.fail("the notte-cli submodule is not checked out")
    build_dir = tmp_path_factory.mktemp("cli-writer")
    overlay = build_dir / "overlay.json"
    target = CLI_DIR / "internal" / "auth" / "zz_sdk_contract_writer_test.go"
    _ = overlay.write_text(json.dumps({"Replace": {str(target): str(WRITER)}}))
    binary = build_dir / ("writer.exe" if sys.platform == "win32" else "writer")
    _ = subprocess.run(
        ["go", "test", "-c", "-overlay", str(overlay), "-o", str(binary), "./internal/auth"],
        cwd=CLI_DIR,
        check=True,
    )
    return binary


def _keychain(*args: str) -> None:
    _ = subprocess.run(["/usr/bin/security", *args], capture_output=True, check=False)


@pytest.fixture
def run_cli(writer: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[RunCli]:
    monkeypatch.setenv("NOTTE_CONFIG_DIR", str(tmp_path))
    monkeypatch.delenv("NOTTE_API_KEY", raising=False)
    monkeypatch.delenv("NOTTE_API_URL", raising=False)

    def run(ops: list[dict[str, str]]) -> None:
        plan = tmp_path / "plan.json"
        _ = plan.write_text(json.dumps(ops))
        env = {**os.environ, "NOTTE_SDK_CONTRACT_PLAN": str(plan)}
        _ = subprocess.run([str(writer), "-test.run", "^TestSDKContractWriter$", "-test.count=1"], env=env, check=True)

    if sys.platform == "darwin":
        for key in STORE_KEYS:
            _keychain("add-generic-password", "-U", "-A", "-s", auth.KEYRING_SERVICE, "-a", key, "-w", "placeholder")
    try:
        yield run
    finally:
        # The system store is shared by the whole machine: remove what was written.
        run(
            [{"op": "delete_api_key", "api_url": url} for url in API_URLS]
            + [{"op": "delete_secret", "key": auth.KEYRING_KEY}]
        )
        if sys.platform == "darwin":
            for key in STORE_KEYS:
                _keychain("delete-generic-password", "-s", auth.KEYRING_SERVICE, "-a", key)


def _clear_placeholders() -> None:
    """Drop the macOS placeholders the CLI did not overwrite, so they cannot be read as keys."""
    if sys.platform != "darwin":
        return
    for key in STORE_KEYS:
        result = subprocess.run(
            ["/usr/bin/security", "find-generic-password", "-s", auth.KEYRING_SERVICE, "-a", key, "-w"],
            capture_output=True,
            check=False,
        )
        if result.stdout.strip() == b"placeholder":
            _keychain("delete-generic-password", "-s", auth.KEYRING_SERVICE, "-a", key)


def _read_system_store(key: str) -> str | None:
    if sys.platform == "darwin":
        return auth._get_from_macos_keychain(key)
    if sys.platform == "win32":
        return auth._get_from_windows_credential_manager(key)
    return auth._get_from_secret_service(key)


def _check_store(values: dict[str, str]) -> None:
    """Check each key with the reader of the store the CLI put it in.

    A full lookup could succeed through another store, so this reads the one
    the CLI used directly. When CI names the store it expects, check that too.
    """
    expected = os.getenv("NOTTE_CLI_CONTRACT_STORE") or None
    assert expected in (None, "file", "secret-service"), f"unknown NOTTE_CLI_CONTRACT_STORE {expected!r}"
    files = Path(os.environ["NOTTE_CONFIG_DIR"]) / ".notte" / "cli"
    for key, value in values.items():
        in_file = (files / key).is_file()
        if expected is not None:
            assert in_file == (expected == "file"), key
        if in_file:
            assert _file_value(key) == value, key
        else:
            assert _read_system_store(key) == value, key


def test_sdk_reads_legacy_key_written_by_cli(run_cli: RunCli) -> None:
    value = f"contract-legacy-{secrets.token_hex(8)}"
    run_cli([{"op": "set_secret", "key": auth.KEYRING_KEY, "value": value}])
    _clear_placeholders()
    _check_store({auth.KEYRING_KEY: value})

    assert auth.get_keyring_api_key("https://api.notte.cc") == value
    assert auth.get_keyring_api_key("https://us-staging.notte.cc") is None


def test_sdk_reads_environment_keys_written_by_cli(run_cli: RunCli) -> None:
    values = {url: f"contract-{secrets.token_hex(8)}" for url in API_URLS}
    run_cli([{"op": "set_api_key", "api_url": url, "value": value} for url, value in values.items()])
    _clear_placeholders()
    _check_store({f"{auth.KEYRING_KEY}:{auth.resolve_env_label(url)}": value for url, value in values.items()})

    for url, value in values.items():
        assert auth.get_keyring_api_key(url) == value, url
    assert auth.get_keyring_api_key("https://us-dev.notte.cc") is None


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS Keychain")
def test_sdk_reads_macos_keychain_item() -> None:
    """The real `security` round trip, for an item stored the way 99designs/keyring stores it."""
    key = f"api_key:contract-{secrets.token_hex(4)}"
    value = f"contract-{secrets.token_hex(8)}"
    _keychain("add-generic-password", "-U", "-A", "-s", auth.KEYRING_SERVICE, "-a", key, "-w", value)
    try:
        assert auth._get_from_macos_keychain(key) == value
    finally:
        _keychain("delete-generic-password", "-s", auth.KEYRING_SERVICE, "-a", key)
    assert auth._get_from_macos_keychain(key) is None


@pytest.mark.skipif(sys.platform != "win32", reason="Windows Credential Manager")
def test_sdk_reads_windows_credential() -> None:
    """The real Credential Manager round trip, for a credential stored the way 99designs/keyring stores it."""
    import ctypes
    from ctypes import wintypes

    from notte_sdk.auth import _get_from_windows_credential_manager

    class Credential(ctypes.Structure):
        _fields_ = [
            ("Flags", wintypes.DWORD),
            ("Type", wintypes.DWORD),
            ("TargetName", wintypes.LPWSTR),
            ("Comment", wintypes.LPWSTR),
            ("LastWritten", wintypes.FILETIME),
            ("CredentialBlobSize", wintypes.DWORD),
            ("CredentialBlob", ctypes.c_char_p),
            ("Persist", wintypes.DWORD),
            ("AttributeCount", wintypes.DWORD),
            ("Attributes", ctypes.c_void_p),
            ("TargetAlias", wintypes.LPWSTR),
            ("UserName", wintypes.LPWSTR),
        ]

    advapi32 = ctypes.WinDLL("advapi32")  # pyright: ignore[reportAttributeAccessIssue]
    key = f"api_key:contract-{secrets.token_hex(4)}"
    value = f"contract-{secrets.token_hex(8)}".encode()
    # danieljoos/wincred, used by 99designs/keyring: generic credential, raw bytes, persisted per user.
    credential = Credential(
        Type=1, TargetName=f"keyring:notte-cli:{key}", CredentialBlobSize=len(value), CredentialBlob=value, Persist=2
    )
    assert advapi32.CredWriteW(ctypes.byref(credential), 0)
    try:
        assert _get_from_windows_credential_manager(key) == value.decode()
    finally:
        _ = advapi32.CredDeleteW(f"keyring:notte-cli:{key}", 1, 0)
    assert _get_from_windows_credential_manager(key) is None
