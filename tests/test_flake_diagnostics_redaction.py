"""Artifact redaction protects off-environment credentials without losing context."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from tests import flake_diagnostics


@pytest.fixture(autouse=True)
def no_environment_values(monkeypatch: pytest.MonkeyPatch) -> None:
    # These cases must exercise generic redaction, not known-value substitution.
    monkeypatch.setattr(flake_diagnostics, "os", SimpleNamespace(environ={}))


@pytest.mark.parametrize(
    "key",
    [
        "client_secret",
        "db_password",
        "OPENAI_API_KEY",
        "authToken",
        "id_token",
        "session_token",
        "clientSecret",
        "dbPassword",
        "client-secret",
        "AUTH_TOKEN",
        "passwd",
        "serviceApiKeyValue",
    ],
)
@pytest.mark.parametrize("separator", ["=", ":"])
def test_prefixed_and_camel_keys_are_redacted_without_environment_values(key: str, separator: str) -> None:
    text = f"ValueError original failure; {key}{separator}off-env-canary session_id=session-123 status=active"
    assert flake_diagnostics.redact(text) == (
        "ValueError original failure; [REDACTED] session_id=session-123 status=active"
    )


@pytest.mark.parametrize("key", ["client_secret", '"client_secret"', "'client_secret'"])
@pytest.mark.parametrize("separator", ["=", ":"])
def test_quoted_keys_and_whitespace_preserve_adjacent_selector(key: str, separator: str) -> None:
    text = f'Error {key} \t{separator} \t"two words", selector=css:button'
    assert flake_diagnostics.redact(text) == "Error [REDACTED], selector=css:button"


@pytest.mark.parametrize(
    "value, terminated",
    [
        ('"two words"', True),
        ("'two words'", True),
        (r'"two \"quoted\" words"', True),
        (r"'two \'quoted\' words'", True),
        (r'"directory\\subdir with spaces"', True),
        ('"two\nwords"', True),
        ('"ends with slash' + "\\\\" + '"', True),
        ('"unterminated two words', False),
        (r'"unterminated escaped \" words', False),
        ('"unterminated trailing ' + "\\", False),
    ],
)
def test_quoted_values_consume_complete_escaped_payload(value: str, terminated: bool) -> None:
    suffix = " session_id=session-123 status=active"
    text = f"RuntimeError original failure; client_secret={value}{suffix}"
    expected_suffix = suffix if terminated else ""
    assert flake_diagnostics.redact(text) == f"RuntimeError original failure; [REDACTED]{expected_suffix}"


@pytest.mark.parametrize("value", ["off-env-canary", r"two\ words", r"path\\piece\ with\ spaces", "opaque+[ab]/=/="])
def test_unquoted_and_escaped_whitespace_values_are_consumed(value: str) -> None:
    text = f"Error db_password={value}; session_id=session-123 selector=css:button"
    assert flake_diagnostics.redact(text) == "Error [REDACTED]; session_id=session-123 selector=css:button"


@pytest.mark.parametrize(
    "text",
    [
        r"password=\"two words\" session_id=abc",  # pragma: allowlist secret
        r"payload=\"{\"client_secret\": \"two words\"}\" session_id=abc",  # pragma: allowlist secret
        r"\"client_secret\": \"two words\" session_id=abc",  # pragma: allowlist secret
        'password="""two words""" session_id=abc',  # pragma: allowlist secret
        "db_password='''two words''' session_id=abc",  # pragma: allowlist secret
        'password=b"two words" session_id=abc',  # pragma: allowlist secret
        'password=r"two words" session_id=abc',  # pragma: allowlist secret
    ],
)
def test_source_representation_quotes_do_not_leave_credential_fragments(text: str) -> None:
    retained = flake_diagnostics.redact(text)
    assert "two" not in retained
    assert "words" not in retained
    assert "[REDACTED]" in retained
    assert retained.endswith(" session_id=abc")


@pytest.mark.parametrize("levels", [1, 2, 3])
@pytest.mark.parametrize("quoted_key", [False, True])
def test_nested_json_escape_levels_preserve_the_complete_value(levels: int, quoted_key: bool) -> None:
    key = '"client_secret"' if quoted_key else "client_secret"
    value = r'"two \"quoted\" words\\"'
    text = f"Original error {key}={value} session_id=abc"
    for _ in range(levels):
        text = json.dumps(text)[1:-1]
    retained = flake_diagnostics.redact(text)
    assert retained == "Original error [REDACTED] session_id=abc"


def test_long_unbroken_text_and_maximal_key_are_scanned_without_backtracking_pattern() -> None:
    opaque = "Az09" * 20_000
    assert flake_diagnostics.redact(opaque) == opaque
    assert flake_diagnostics.redact(f"{opaque}_token=off-env-canary status=active") == "[REDACTED] status=active"
    assert flake_diagnostics.redact(f"client_secret={opaque} session_id=abc") == "[REDACTED] session_id=abc"


def test_sensitive_json_values_are_redacted_recursively() -> None:
    payload = {
        "session_id": "session-123",
        "status": "active",
        "error": "Original scrape failure",
        "selectors": {"css_selector": "html > body > button"},
        "nested": [
            {"client_secret": "off-env-client-canary", "id_token": "off-env-token-canary"},  # pragma: allowlist secret
            {"dbPassword": {"wrapped": "off-env-password-canary"}},
        ],
    }
    retained = flake_diagnostics.redact_json(payload)
    assert retained == {
        **payload,
        "nested": [
            {"client_secret": "[REDACTED]", "id_token": "[REDACTED]"},
            {"dbPassword": "[REDACTED]"},
        ],
    }
    assert "off-env-" not in json.dumps(retained)


def test_persisted_text_and_json_artifacts_preserve_useful_evidence(tmp_path: Path) -> None:
    item = MagicMock(spec=pytest.Item)
    item.nodeid = "tests/integration/sdk/test_scraping.py::test_sdk_scraping_markdown"
    item.config = MagicMock()
    item.config.rootpath = tmp_path
    item.execution_count = 1
    state = flake_diagnostics.Diagnostics()
    directory = state.write(
        item,
        "call",
        {
            "failure.txt": 'ValueError scrape failed client_secret="off-env two words"; session_id=session-123',  # pragma: allowlist secret
            "events.txt": "requestfailed id_token=off-env-token; status=503",
            "session.json": json.dumps(
                {
                    "session_id": "session-123",
                    "status": "active",
                    "client_secret": "off-env-json-canary",  # pragma: allowlist secret
                    "error": 'original failure db_password="off-env escaped \\"value\\" words"',  # pragma: allowlist secret
                    "selector": "css=button",
                }
            ),
        },
    )
    assert (directory / "failure.txt").read_text() == "ValueError scrape failed [REDACTED]; session_id=session-123"
    assert (directory / "events.txt").read_text() == "requestfailed [REDACTED]; status=503"
    assert json.loads((directory / "session.json").read_text()) == {
        "session_id": "session-123",
        "status": "active",
        "client_secret": "[REDACTED]",
        "error": "original failure [REDACTED]",
        "selector": "css=button",
    }
    assert "off-env" not in "\n".join(path.read_text() for path in directory.iterdir())


@pytest.mark.parametrize("name", ["failure.txt", "result.json"])
def test_assignment_redaction_happens_before_artifact_truncation(name: str) -> None:
    prefix = 63_960 if name.endswith(".json") else 63_975
    value = "x" * prefix + ' client_secret="off-env canary words"' + "y" * 100  # pragma: allowlist secret
    text = json.dumps({"error": value}) if name.endswith(".json") else value
    assert text.index("off-env") < 64_000 < text.index("off-env") + len("off-env canary words")
    state = flake_diagnostics.Diagnostics()
    state.record(name, lambda: text)
    retained = state.files[name]
    assert json.loads(retained)["truncated"] is True
    assert "off-env" not in retained
    assert "canary" not in retained
    assert "words" not in retained
