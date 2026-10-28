"""Manual cleanup selection and existing deletion guards, entirely offline."""

import datetime as dt
import json
import os
import re
import subprocess
from pathlib import Path
from types import SimpleNamespace

import notte_sdk
import pytest
import yaml

from scripts import ci_vault_scope as scope

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/cleanup-ci-vaults.yml"
STAGING = "https://us-staging.notte.cc"
DEV = "https://us-dev.notte.cc"
PROD = "https://api.notte.cc"
FIXTURE_VALUE = "selected-credential-fixture"
CONFIG = yaml.safe_load(WORKFLOW.read_text())
INPUTS = CONFIG[True]["workflow_dispatch"]["inputs"]
STEPS = {step["name"]: step for step in CONFIG["jobs"]["cleanup"]["steps"]}


def run_step(name: str, env: dict[str, str], directory: Path):
    return subprocess.run(
        ["bash", "-e", "-o", "pipefail", "-c", STEPS[name]["run"]],
        env={"PATH": os.environ["PATH"], **env},
        cwd=directory,
        capture_output=True,
        text=True,
        timeout=5,
    )


@pytest.mark.parametrize("url", [STAGING, DEV, PROD, "https://other.example"])
@pytest.mark.parametrize("key", INPUTS["api_key_secret"]["options"] + ["UNRELATED_SECRET", ""])
@pytest.mark.parametrize("allow", ["false", "true"])
def test_only_documented_environment_key_guard_combinations_pass(
    tmp_path: Path, url: str, key: str, allow: str
) -> None:
    result = run_step(
        "Validate environment and credential selection",
        {
            "NOTTE_API_URL": url,
            "API_KEY_SECRET": key,
            "ALLOW_PRODUCTION": allow,
        },
        tmp_path,
    )
    compatible = key == "NOTTE_API_KEY" or (url == STAGING and key in INPUTS["api_key_secret"]["options"])
    expected = url in {STAGING, DEV, PROD} and compatible and (allow == "true") == (url == PROD)
    assert (result.returncode == 0) is expected, result.stdout + result.stderr


@pytest.fixture
def fake_python(tmp_path: Path):
    executable = tmp_path / "python"
    executable.write_text(
        "#!/usr/bin/env python3\nimport json, os, sys\n"
        "from pathlib import Path\n"
        "Path('invocation.json').write_text(json.dumps({'args': sys.argv[1:], 'url': os.environ['NOTTE_API_URL'], 'key': os.environ['NOTTE_API_KEY']}))\n"
    )
    executable.chmod(0o755)
    return tmp_path


def cleanup(directory: Path, **overrides: str):
    env = {
        "PATH": str(directory) + os.pathsep + os.environ["PATH"],
        "PYTHONPATH": str(ROOT),
        "NOTTE_API_URL": STAGING,
        "API_KEY_SECRET": INPUTS["api_key_secret"]["options"][1],
        "NOTTE_API_KEY": FIXTURE_VALUE,
        "ALLOW_PRODUCTION": "false",
        "MODE": "prefix",
        "PREFIX": "ci-123-execution",
        "MIN_AGE_HOURS": "2",
        "DRY_RUN": "false",
        **overrides,
    }
    validation = run_step("Validate environment and credential selection", env, directory)
    return validation if validation.returncode else run_step("Cleanup vaults", env, directory)


@pytest.mark.parametrize("dry_run", ["false", "true"])
@pytest.mark.parametrize("production", [False, True])
def test_command_keeps_selected_environment_credential_prefix_and_override(
    fake_python: Path, dry_run: str, production: bool
):
    overrides = {"DRY_RUN": dry_run}
    if production:
        overrides.update(
            NOTTE_API_URL=PROD, API_KEY_SECRET=INPUTS["api_key_secret"]["default"], ALLOW_PRODUCTION="true"
        )
    assert cleanup(fake_python, **overrides).returncode == 0
    invocation = json.loads((fake_python / "invocation.json").read_text())
    assert invocation["url"] == (PROD if production else STAGING)
    assert invocation["key"] == FIXTURE_VALUE
    expected = ["scripts/cleanup_ci_vaults.py"]
    if production:
        expected.append("--allow-production")
    if dry_run == "true":
        expected.append("--dry-run")
    expected.extend(["--prefix", "ci-123-execution"])
    assert invocation["args"] == expected


@pytest.mark.parametrize(
    "updates",
    [
        {"NOTTE_API_KEY": ""},
        {"PREFIX": ""},
        {"DRY_RUN": "invalid"},
        {"MODE": "invalid"},
        {"NOTTE_API_URL": PROD},
        {"NOTTE_API_URL": PROD, "ALLOW_PRODUCTION": "true"},
    ],
)
def test_missing_key_invalid_inputs_and_mismatched_production_never_invoke_cleanup(fake_python: Path, updates):
    assert cleanup(fake_python, **updates).returncode != 0
    assert not (fake_python / "invocation.json").exists()


def test_orphan_mode_keeps_age_and_dry_run_arguments(fake_python: Path):
    assert cleanup(fake_python, MODE="orphan-defaults", MIN_AGE_HOURS="6", DRY_RUN="true").returncode == 0
    args = json.loads((fake_python / "invocation.json").read_text())["args"]
    assert args == ["scripts/cleanup_ci_vaults.py", "--dry-run", "--orphan-defaults", "--min-age-hours", "6"]


@pytest.fixture
def fake_client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    deleted: list[str] = []
    now = dt.datetime.now(dt.timezone.utc)
    vaults = [
        SimpleNamespace(vault_id="owned", name="ci-123-execution-abcd", for_persona=False, created_at=now),
        SimpleNamespace(vault_id="other", name="ci-456-other-abcd", for_persona=False, created_at=now),
        SimpleNamespace(vault_id="persona", name="ci-123-execution-persona", for_persona=True, created_at=now),
        SimpleNamespace(
            vault_id="old-default", name="default", for_persona=False, created_at=now - dt.timedelta(hours=4)
        ),
        SimpleNamespace(vault_id="new-default", name="default", for_persona=False, created_at=now),
        SimpleNamespace(
            vault_id="persona-default", name="default", for_persona=True, created_at=now - dt.timedelta(hours=4)
        ),
    ]
    client = SimpleNamespace(
        vaults=SimpleNamespace(
            server_url=STAGING,
            list=lambda **kwargs: vaults,
            delete=lambda vault_id: deleted.append(vault_id),
        )
    )
    monkeypatch.setattr(notte_sdk, "NotteClient", lambda: client)
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    return client, deleted


@pytest.mark.parametrize("allow", [False, True])
def test_resolved_production_url_still_requires_explicit_override(fake_client, allow: bool):
    client, deleted = fake_client
    client.vaults.server_url = PROD
    if allow:
        assert scope.cleanup_this_run(prefix="ci-123-execution", allow_production=True) == 0
        assert deleted == ["owned"]
    else:
        with pytest.raises(SystemExit, match="Refusing to delete vaults from production"):
            scope.cleanup_this_run(prefix="ci-123-execution")
        assert deleted == []


def test_prefix_persona_age_and_dry_run_guards_are_preserved(fake_client):
    _, deleted = fake_client
    assert scope.cleanup_this_run(prefix="ci-123-execution", dry_run=True) == 0
    assert deleted == []
    assert scope.cleanup_this_run(prefix="ci-123-execution") == 0
    assert deleted == ["owned"]
    deleted.clear()
    assert scope.cleanup_orphan_defaults(dry_run=True, min_age_hours=2) == 0
    assert deleted == []
    assert scope.cleanup_orphan_defaults(dry_run=False, min_age_hours=-1) == 2
    assert deleted == []
    assert scope.cleanup_orphan_defaults(dry_run=False, min_age_hours=2) == 0
    assert deleted == ["old-default"]


def test_dispatch_uses_exact_named_secret_and_explicit_environment_on_reviewed_main():
    assert set(CONFIG[True]) == {"workflow_dispatch"}
    assert INPUTS["api_url"]["default"] == STAGING
    assert INPUTS["allow_production"]["default"] is False
    job = CONFIG["jobs"]["cleanup"]
    assert "github.ref == 'refs/heads/main'" in job["if"]
    assert job["env"]["NOTTE_API_URL"] == "${{ inputs.api_url }}"
    expression = STEPS["Cleanup vaults"]["env"]["NOTTE_API_KEY"]
    assert re.search(r"\bsecrets\s*\[", WORKFLOW.read_text()) is None
    assert set(re.findall(r"\bsecrets\.(\w+)", expression)) == set(INPUTS["api_key_secret"]["options"])
    assert len(INPUTS["api_key_secret"]["options"]) == 6
    clauses = [
        f"(inputs.api_key_secret == ('{name}') && secrets.{name})" for name in INPUTS["api_key_secret"]["options"]
    ]
    assert expression == "${{ " + " || ".join(clauses) + " || '' }}"
    assert CONFIG["permissions"] == {"contents": "read"}


@pytest.mark.parametrize("requested", INPUTS["api_key_secret"]["options"] + ["UNRELATED_SECRET", ""])
@pytest.mark.parametrize("available", [False, True])
def test_static_secret_selection_uses_only_requested_credential_without_fallback(
    fake_python: Path, requested: str, available: bool
) -> None:
    values = {name: f"fixture-{index}" for index, name in enumerate(INPUTS["api_key_secret"]["options"])}
    if not available:
        values[requested] = ""
    expression = STEPS["Cleanup vaults"]["env"]["NOTTE_API_KEY"][3:-2]
    expression = expression.replace("inputs.api_key_secret", repr(requested))
    expression = re.sub(r"\bsecrets\.(\w+)", lambda match: repr(values.get(match[1], "")), expression)
    expression = expression.replace("&&", "and").replace("||", "or")
    selected = eval(expression, {"__builtins__": {}})
    expected = values[requested] if requested in INPUTS["api_key_secret"]["options"] else ""
    assert selected == expected
    result = cleanup(fake_python, API_KEY_SECRET=requested, NOTTE_API_KEY=selected)
    assert (result.returncode == 0) is bool(expected)
    invocation = fake_python / "invocation.json"
    if expected:
        assert json.loads(invocation.read_text())["key"] == expected
    else:
        assert not invocation.exists()


@pytest.mark.parametrize(
    "prefix,allowed",
    [
        ("ci-32862931541-execution", True),
        ("ci-40619044502-staging-and-live-1-4", True),
        ("ci-40619044502-_custom_job", True),
        (scope.sanitize_prefix("ci-40619044502-" + "x" * 50), True),
        ("default", False),
        ("ci-", False),
        ("ci-4061", False),
        ("ci-40619044502-", False),
        ("arbitrary", False),
        ("ci-0-execution", False),
        ("ci-123-execution-", False),
        ("ci-123-execution/1", False),
        ("ci-40619044502-" + "x" * 50, False),
        ("ci-" + "1" * 38 + "-job", False),
    ],
)
def test_production_prefix_must_name_a_complete_ci_run_without_sanitization(
    fake_python: Path, prefix: str, allowed: bool
) -> None:
    result = cleanup(
        fake_python,
        NOTTE_API_URL=PROD,
        API_KEY_SECRET=INPUTS["api_key_secret"]["default"],
        ALLOW_PRODUCTION="true",
        PREFIX=prefix,
    )
    assert (result.returncode == 0) is allowed, result.stdout + result.stderr
    invocation = fake_python / "invocation.json"
    if allowed:
        args = json.loads(invocation.read_text())["args"]
        assert args == ["scripts/cleanup_ci_vaults.py", "--allow-production", "--prefix", prefix]
    else:
        assert "Production prefix cleanup requires" in result.stderr
        assert not invocation.exists()


@pytest.mark.parametrize("url", [STAGING, DEV])
@pytest.mark.parametrize("prefix", ["default", "ci-", "ci-123"])
def test_nonproduction_prefix_behavior_is_preserved(fake_python: Path, url: str, prefix: str) -> None:
    assert (
        cleanup(
            fake_python, NOTTE_API_URL=url, API_KEY_SECRET=INPUTS["api_key_secret"]["default"], PREFIX=prefix
        ).returncode
        == 0
    )
    args = json.loads((fake_python / "invocation.json").read_text())["args"]
    assert args == ["scripts/cleanup_ci_vaults.py", "--prefix", prefix]


@pytest.mark.parametrize("dry_run", ["false", "true"])
def test_production_orphan_mode_preserves_explicit_age_and_dry_run(fake_python: Path, dry_run: str) -> None:
    assert (
        cleanup(
            fake_python,
            NOTTE_API_URL=PROD,
            API_KEY_SECRET=INPUTS["api_key_secret"]["default"],
            ALLOW_PRODUCTION="true",
            MODE="orphan-defaults",
            PREFIX="default",
            MIN_AGE_HOURS="6",
            DRY_RUN=dry_run,
        ).returncode
        == 0
    )
    args = json.loads((fake_python / "invocation.json").read_text())["args"]
    expected = ["scripts/cleanup_ci_vaults.py", "--allow-production"]
    if dry_run == "true":
        expected.append("--dry-run")
    assert args == expected + ["--orphan-defaults", "--min-age-hours", "6"]


def test_production_default_prefix_is_refused_even_for_dry_run(fake_python: Path) -> None:
    assert (
        cleanup(
            fake_python,
            NOTTE_API_URL=PROD,
            API_KEY_SECRET=INPUTS["api_key_secret"]["default"],
            ALLOW_PRODUCTION="true",
            PREFIX="default",
            DRY_RUN="true",
        ).returncode
        != 0
    )
    assert not (fake_python / "invocation.json").exists()
