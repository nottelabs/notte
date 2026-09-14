"""Exercise version transitions without importing or installing the SDK."""

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]
spec = importlib.util.spec_from_file_location("release_version", ROOT / "scripts/release_version.py")
assert spec and spec.loader
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    (tmp_path / "packages/notte-core").mkdir(parents=True)
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "notte"\nversion = "1.9.1.dev0"\n'
        'dependencies = ["notte-core==1.9.1.dev0", "unrelated==1.9.1.dev0"]\n'
        '[project.optional-dependencies]\nextra = ["notte_core==1.9.1.dev0"]\n'
    )
    (tmp_path / "packages/notte-core/pyproject.toml").write_text(
        '[project]\nname = "notte-core"\nversion = "1.9.1.dev0"\n'
    )
    return tmp_path


@pytest.mark.parametrize("current", ["1.9.1.dev", "1.9.1.dev0", "1.9.1"])
@pytest.mark.parametrize("tag", ["v1.9.1", "1.9.1"])
def test_release_normalizes_matching_versions_and_internal_pins(workspace: Path, current: str, tag: str) -> None:
    for path in workspace.rglob("pyproject.toml"):
        path.write_text(path.read_text().replace("1.9.1.dev0", current))
    release.run("release", tag, workspace)
    version, texts = release.workspace(workspace)
    assert version == "1.9.1"
    assert '"notte-core==1.9.1"' in texts[workspace / "pyproject.toml"]
    assert '"notte_core==1.9.1"' in texts[workspace / "pyproject.toml"]
    assert f'"unrelated=={current}"' in texts[workspace / "pyproject.toml"]


@pytest.mark.parametrize("tag", ["v1.9.2", "v1.9.0", "v1.9.1.dev0", "v1.9.1rc1", "v01.9.1", "bad"])
def test_invalid_release_leaves_every_file_untouched(workspace: Path, tag: str) -> None:
    before = {path: path.read_bytes() for path in workspace.rglob("pyproject.toml")}
    with pytest.raises(ValueError):
        release.run("release", tag, workspace)
    assert before == {path: path.read_bytes() for path in before}


@pytest.mark.parametrize("mismatch", ["package", "pin"])
def test_inconsistent_workspace_fails_before_any_write(workspace: Path, mismatch: str) -> None:
    path = workspace / ("packages/notte-core/pyproject.toml" if mismatch == "package" else "pyproject.toml")
    if mismatch == "package":
        path.write_text(path.read_text().replace("1.9.1.dev0", "1.9.0.dev0"))
    else:
        path.write_text(path.read_text().replace("notte-core==1.9.1.dev0", "notte-core==1.9.0.dev0"))
    before = {path: path.read_bytes() for path in workspace.rglob("pyproject.toml")}
    with pytest.raises(ValueError):
        release.run("release", "v1.9.1", workspace)
    assert before == {path: path.read_bytes() for path in before}


def test_next_patch_is_idempotent_and_older_releases_cannot_regress_main(workspace: Path) -> None:
    release.run("next", "v1.9.1", workspace)
    assert release.workspace(workspace)[0] == "1.9.2.dev0"
    release.run("next", "v1.9.1", workspace)
    release.run("next", "v1.8.99", workspace)
    assert release.workspace(workspace)[0] == "1.9.2.dev0"
    with pytest.raises(ValueError, match="behind release"):
        release.run("next", "v1.10.0", workspace)


def test_validate_does_not_strip_dev_suffix(workspace: Path) -> None:
    release.run("validate", "v1.9.1", workspace)
    assert release.workspace(workspace)[0] == "1.9.1.dev0"


def test_build_rejects_mismatched_tag_before_cleaning_dist_or_calling_uv(workspace: Path) -> None:
    (workspace / "scripts").mkdir()
    (workspace / "scripts/release_version.py").write_bytes((ROOT / "scripts/release_version.py").read_bytes())
    (workspace / "dist").mkdir()
    sentinel = workspace / "dist/existing.whl"
    sentinel.touch()
    result = subprocess.run(["bash", str(ROOT / "build.sh"), "v1.9.2"], cwd=workspace, capture_output=True, text=True)
    assert result.returncode != 0
    assert "does not match" in result.stderr
    assert sentinel.exists()


def test_cli_rejects_invalid_tag() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/release_version.py"), "validate", "not-a-version"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "Expected a stable" in result.stderr


@pytest.mark.parametrize("exit_code", [0, 42])
@pytest.mark.parametrize("use_make", [False, True])
def test_local_build_restores_preexisting_edits_and_lockfile(workspace: Path, exit_code: int, use_make: bool) -> None:
    import os

    scripts = workspace / "scripts"
    scripts.mkdir()
    for name in ("release_version.py", "build_release.py"):
        (scripts / name).write_bytes((ROOT / "scripts" / name).read_bytes())
    for name in ("build.sh", "makefile"):
        (workspace / name).write_bytes((ROOT / name).read_bytes())
    (workspace / "uv.lock").write_text("original lockfile\n")
    for manifest in workspace.rglob("pyproject.toml"):
        manifest.write_text(manifest.read_text() + "\n# pre-existing local edit\n")
    originals = {path: path.read_bytes() for path in [*workspace.rglob("pyproject.toml"), workspace / "uv.lock"]}
    fake_bin = workspace / "bin"
    fake_bin.mkdir()
    uv = fake_bin / "uv"
    uv.write_text(f'#!/bin/sh\nprintf changed > "$TEST_WORKSPACE/uv.lock"\nexit {exit_code}\n')
    uv.chmod(0o755)
    command = ["make", "release", "1.9.1"] if use_make else [sys.executable, str(scripts / "build_release.py"), "1.9.1"]
    result = subprocess.run(
        command,
        cwd=workspace,
        env={**os.environ, "PATH": f"{fake_bin}:{os.environ['PATH']}", "TEST_WORKSPACE": str(workspace)},
        capture_output=True,
        text=True,
    )
    if use_make:
        assert (result.returncode == 0) == (exit_code == 0)
        if exit_code:
            assert f"Error {exit_code}" in result.stderr
    else:
        assert result.returncode == exit_code
    assert originals == {path: path.read_bytes() for path in originals}
