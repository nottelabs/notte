"""Select CI suites from the complete PR or push diff, without project dependencies."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import cast

GROUPS = {
    "python": {"python_static", "python_unit", "python_live", "llm_provider_live", "python_docs", "cli_contract"},
    "node": {"node_static", "node_live", "node_generated"},
    "docs": {"docs_static", "docs_live"},
    "paired": {"paired_static", "paired_live"},
    "readme": {"readme_static", "readme_live"},
}
ALL = {name for group in GROUPS.values() for name in group}
PYTHON_RUNTIME = {"python_static", "python_unit", "python_live"}
PYTHON_LIVE_TESTS = {
    "tests/actions/test_execution.py",
    "tests/browser/test_build_dom_tree_pointer_elements.py",
    "tests/browser/test_clipboard_isolation.py",
    "tests/llm/test_provider_matrix.py",
    "tests/llm/test_schema_scraping.py",
    "tests/llm/test_structured_output.py",
    "tests/test_fetch_helper.py",
    "tests/test_goto_wait_until.py",
    "tests/test_session.py",
    "tests/test_trajectory.py",
}
SDK_EXAMPLES = {"docs_static"} | GROUPS["paired"] | GROUPS["readme"]
POLICY = {"scripts/ci_scope.py", "tests/scripts/test_ci_scope.py"}
PYTHON_CONFIG = {"pyproject.toml", "uv.lock", ".python-version"}
NODE_CONFIG = {"node-sdk/package.json", "node-sdk/package-lock.json"}
INTEGRATION_INPUTS = {
    "scripts/integration_examples.json",
    "scripts/ci_integration_examples.py",
    "tests/scripts/test_ci_integration_examples.py",
}
INTEGRATION_EXAMPLES: dict[str, str] = json.loads(Path(__file__).with_name("integration_examples.json").read_text())
RECIPE_INPUTS = {
    "docs/package.json": {"claude-agents", "mongodb", "openai-agents"},
    "docs/package-lock.json": {"claude-agents", "mongodb", "openai-agents"},
    "docs/src/sniptest/run_python.py": {"agent-browser", "mongodb"},
    "docs/src/sniptest/run_typescript.mjs": {"agent-browser", "mongodb"},
    "docs/src/sniptest/typescript-loader.mjs": {"agent-browser", "mongodb"},
    "node-sdk/test/helpers/run-openai-recipe.py": {"openai-agents"},
    "node-sdk/test/helpers/session-closure.ts": {"agent-browser", "mongodb"},
    "node-sdk/test/agent-browser.recipe.test.ts": {"agent-browser"},
    "tests/docs/test_agent_browser_recipe.py": {"agent-browser"},
    ".github/workflows/selector-repair.yml": {"github-actions"},
    "docs/src/integrations/github-actions.mdx": {"github-actions"},
}
for _recipe in ("agent-browser", "claude-agents", "mongodb", "openai-agents"):
    RECIPE_INPUTS[f"node-sdk/test/{_recipe}.integration.test.ts"] = {_recipe}
    for _language in ("py", "ts"):
        RECIPE_INPUTS[f"docs/src/testers/integrations/{_recipe.replace('-', '_')}.{_language}"] = {_recipe}
NODE_GENERATION = {
    "node-sdk/openapi-ts.config.ts",
    "node-sdk/src/proxy/patterns.ts",
    "node-sdk/src/resources.gen.ts",
    "node-sdk/scripts/check-generated-drift.js",
    "node-sdk/scripts/normalize-generated.js",
    "node-sdk/scripts/generate-proxy-patterns.js",
    "node-sdk/scripts/generate-resources.mjs",
}
WORKFLOWS = {
    "test-cicd.yml": "python",
    "node-sdk-ci.yml": "node",
    "docs-tests-cicd.yml": "docs",
    "paired-sdk-examples.yml": "paired",
    "readme-check.yml": "readme",
}
INTEGRATION_WORKFLOWS = {
    "agent-browser-integration.yml",
    "agentcard-integration.yml",
    "anthropic-computer-use-integration.yml",
    "box-integration.yml",
    "braintrust-integration.yml",
    "claude-agents-integration.yml",
    "deepagents-integration.yml",
    "docker-sandboxes-integration.yml",
    "e2e-integration.yml",
    "eve-integration.yml",
    "evervault-integration.yml",
    "fx-integration.yml",
    "github-actions-integration.yml",
    "inngest-integration.yml",
    "laminar-integration.yml",
    "mongodb-integration.yml",
    "onepassword-integration.yml",
    "openagi-integration.yml",
    "openai-agents-integration.yml",
    "pipedream-integration.yml",
    "prime-intellect-integration.yml",
    "replit-integration.yml",
    "selenium-integration.yml",
    "selector-repair.yml",
    "stripe-link-integration.yml",
    "temporal-integration.yml",
    "terraform-profiles-integration.yml",
    "trigger-integration.yml",
    "tzafon-integration.yml",
    "valtown-integration.yml",
    "watsonx-integration.yml",
    "yutori-integration.yml",
}


def integration_examples_for_path(path: str) -> set[str]:
    """Native projects share SDK/build inputs, but do not run for project prose."""
    if path in INTEGRATION_INPUTS | PYTHON_CONFIG | NODE_CONFIG or path in {
        ".github/workflows/paired-sdk-examples.yml",
        "node-sdk/tsconfig.json",
        "node-sdk/tsup.config.ts",
    }:
        return set(INTEGRATION_EXAMPLES)
    if path.startswith(("packages/notte-sdk/", "packages/notte-core/", "src/")):
        return set() if path.endswith(("/README.md", "/CHANGELOG.md")) else set(INTEGRATION_EXAMPLES)
    if path.startswith("node-sdk/") and not path.startswith("node-sdk/test/"):
        return set() if path.endswith((".md", ".mdx", ".txt")) else set(INTEGRATION_EXAMPLES)
    if path.startswith(".github/actions/python-setup/"):
        return set(INTEGRATION_EXAMPLES)
    if path in RECIPE_INPUTS:
        return RECIPE_INPUTS[path] & INTEGRATION_EXAMPLES.keys()
    for name in INTEGRATION_EXAMPLES:
        if path == f".github/workflows/{name}-integration.yml":
            return {name}
        if path == f"examples/{name}/requirements.txt":
            return {name}
        if path.startswith(f"examples/{name}/"):
            prose = path.endswith((".md", ".mdx", ".txt", ".png", ".jpg", ".svg", ".pdf"))
            return set() if prose or path.endswith("/.gitignore") else {name}
    return set()


def native_example_input(path: str) -> bool:
    return path in INTEGRATION_INPUTS or any(
        path.startswith(f"examples/{name}/") or path == f".github/workflows/{name}-integration.yml"
        for name in INTEGRATION_EXAMPLES
    )


def base_scopes_for_path(path: str, *, code_changed: bool = True) -> set[str]:
    """Unknown inputs select broad coverage. Rules combine across every changed path."""
    if path in POLICY or path.startswith(".github/actions/ci-scope/"):
        return ALL.copy()
    if native_example_input(path) and integration_examples_for_path(path):
        return {"python_static", "python_unit"} | GROUPS["paired"]
    if path.startswith(".github/actions/wait-for-api/"):
        return ALL.copy()
    if path.startswith(".github/actions/python-setup/"):
        return GROUPS["python"] | SDK_EXAMPLES
    if path.startswith(".github/workflows/"):
        name = path.removeprefix(".github/workflows/")
        if name in INTEGRATION_WORKFLOWS:
            # Dedicated integration workflows cover these standalone changes.
            # SDK changes in the same diff still select the SDK's live suites.
            return {"python_static", "python_unit"}
        family = WORKFLOWS.get(name)
        return GROUPS[family].copy() if family else ALL.copy()
    if path in PYTHON_CONFIG:
        return GROUPS["python"] | SDK_EXAMPLES
    if path in NODE_CONFIG:
        return GROUPS["node"] | GROUPS["paired"] | GROUPS["readme"]
    if path == ".pre-commit-config.yaml":
        return {"python_static"}
    if path == "notte-cli":
        return {"cli_contract"}
    if path == "README.md":
        return {"python_static", "readme_static"} | ({"readme_live"} if code_changed else set())
    if path.startswith("docs/"):
        selected = {"python_static", "python_docs", "docs_static", "paired_static"}
        if path in {"docs/src/docs.json", "docs/src/scripts/generate_llms.py"}:
            return selected
        if path.endswith((".md", ".mdx")) and path.startswith(
            (
                "docs/src/sdk-reference/",
                "docs/src/typescript-sdk-reference/",
                "docs/src/cli-reference/",
                "docs/src/api-reference/",
            )
        ):
            return selected
        # The execution harness runs testers, not prose or generated reference pages.
        if path.startswith(("docs/src/testers/", "docs/src/tests/")) or path == "docs/src/conftest.py":
            selected |= GROUPS["docs"]
        if path.startswith(("docs/src/testers/", "docs/src/sniptest/")):
            selected |= GROUPS["paired"]
        if path.endswith((".md", ".mdx")) and code_changed:
            selected |= {"docs_live"}
        # New executable/configuration files may be inputs to either harness.
        if not path.endswith(
            (
                ".md",
                ".mdx",
                ".txt",
                ".png",
                ".jpg",
                ".jpeg",
                ".svg",
                ".ico",
                ".webp",
                ".gif",
                ".woff",
                ".woff2",
                ".ttf",
                ".otf",
                ".pdf",
            )
        ):
            selected |= GROUPS["docs"] | GROUPS["paired"] | {"python_unit"}
        return selected
    if path.startswith("packages/notte-llm/") and not path.endswith(("README.md", "CHANGELOG.md")):
        return (
            PYTHON_RUNTIME
            | {"llm_provider_live"}
            | GROUPS["readme"]
            | ({"cli_contract"} if path.endswith("/pyproject.toml") else set())
        )
    if path.startswith("packages/notte-core/src/notte_core/") and path.split("/")[4] in {
        "extraction.py",
        "schema.py",
        "data.py",
        "pruning.py",
        "errors.py",
        "types.py",
        "pruning",
        "schema",
        "extraction",
    }:
        return PYTHON_RUNTIME | {"llm_provider_live"} | SDK_EXAMPLES
    if path.startswith("tests/llm/") or path.startswith("tests/golden/snapshots/"):
        return PYTHON_RUNTIME | {"llm_provider_live"}
    if path == ".github/scripts/configure_llm.py" or path == "scripts/llm_matrix_report.py":
        return {"python_static", "python_unit", "llm_provider_live"}
    if path.startswith(("packages/", "src/")):
        if path.rsplit("/", 1)[-1] in {"README.md", "CHANGELOG.md"}:
            return {"python_static"}
        selected = PYTHON_RUNTIME | GROUPS["readme"]
        if path.startswith(("packages/notte-sdk/", "packages/notte-core/", "src/")):
            selected |= SDK_EXAMPLES
        if path == "packages/notte-sdk/src/notte_sdk/auth.py" or path.endswith("/pyproject.toml"):
            selected |= {"cli_contract"}
        return selected
    if path.startswith("node-sdk/"):
        if path in {"node-sdk/README.md", "node-sdk/CHANGELOG.md"}:
            return set()
        if path in {
            "node-sdk/scripts/check-package.js",
            "node-sdk/scripts/generate-reference.mjs",
            "node-sdk/scripts/generate-reference.test.mjs",
        }:
            return {"node_static"}
        if path.startswith("node-sdk/test/"):
            selected = {"node_static"}
            if ".integration.test." in path or path.endswith("/integration.test.ts") or "/helpers/" in path:
                selected |= {"node_live"}
            if "docs-snippets" in path or "/helpers/" in path:
                selected |= GROUPS["paired"]
            return selected
        selected = {"node_static", "node_live"} | GROUPS["paired"] | GROUPS["readme"]
        if path.startswith("node-sdk/src/lib/") or path in NODE_GENERATION:
            selected |= {"node_generated"}
        elif not path.startswith("node-sdk/src/") and path not in {
            "node-sdk/tsconfig.json",
            "node-sdk/tsup.config.ts",
            "node-sdk/vitest.config.ts",
        }:
            # Future build/generation inputs must not silently miss drift validation.
            selected |= {"node_generated"}
        return selected
    if path.startswith("tests/"):
        if path.startswith("tests/sdk/cli_contract/") or path == "tests/sdk/test_cli_keyring_contract.py":
            return {"python_static", "python_unit", "cli_contract"}
        if path.startswith("tests/docs/") or path == "tests/test_generate_llms_offline.py":
            return {"python_static", "python_docs"}
        if path in {"tests/examples/test_readme.py", "tests/scripts/test_readme_blocks.py"}:
            return {"python_static", "python_unit"} | GROUPS["readme"]
        if path.startswith("tests/integration/"):
            return PYTHON_RUNTIME.copy()
        # README examples run under tests/conftest.py and its shared config.
        if path in {"tests/conftest.py", "tests/test_notte_config.toml"}:
            return PYTHON_RUNTIME | {"llm_provider_live"} | GROUPS["readme"]
        if path.startswith(("tests/data/", "tests/mock/")) or path in {
            "tests/ci_shard.py",
            "tests/ci_smtp.py",
        }:
            return PYTHON_RUNTIME.copy()
        if path in PYTHON_LIVE_TESTS:
            return PYTHON_RUNTIME.copy()
        if path.rsplit("/", 1)[-1].startswith("test_"):
            return {"python_static", "python_unit"}
        return PYTHON_RUNTIME.copy()
    if path == "scripts/readme_blocks.py":
        return {"python_static", "python_unit"} | GROUPS["readme"]
    if path in {"scripts/ci_vault_scope.py", "scripts/cleanup_ci_vaults.py"}:
        return PYTHON_RUNTIME | GROUPS["docs"]
    if path.startswith("scripts/"):
        return ALL.copy()
    if path.startswith(("examples/", "profiling/", "typing_cases/")):
        return {"python_static", "python_unit"}
    if path in {"browserarena", "notte-skills", "templates"} or path.startswith(("integrations/", "example-apps/")):
        return set()
    if path.startswith(".github/") or path in {"LICENSE", ".gitignore", ".gitmodules"} or path.endswith(".md"):
        return {"python_static"}
    return ALL.copy()


def git(*args: str) -> bytes:
    return subprocess.check_output(["git", *args], stderr=subprocess.PIPE, timeout=30)


def fenced_code(text: str) -> list[list[str]]:
    """Ignore surrounding prose, retaining fence language/options and exact code."""
    blocks: list[list[str]] = []
    block: list[str] | None = None
    fence = ""
    for line in text.splitlines(keepends=True):
        stripped = line.lstrip()
        if block is None:
            match = re.match(r"(`{3,}|~{3,})", stripped)
            if match:
                fence = match[0]
                block = [line]
        else:
            block.append(line)
            if re.fullmatch(re.escape(fence[0]) + "{" + str(len(fence)) + r",}\s*", stripped):
                blocks.append(block)
                block = None
    if block is not None:
        blocks.append(block)
    return blocks


def changed_code(base: str, head: str, path: str) -> bool:
    def content(sha: str) -> str:
        entry = git("--literal-pathspecs", "ls-tree", "-z", sha, "--", path)
        if not entry:
            return ""
        if not entry.startswith((b"100644 blob ", b"100755 blob ")):
            raise ValueError("documentation input is not a regular file")
        return git("show", f"{sha}:{path}").decode("utf-8")

    try:
        return fenced_code(content(base)) != fenced_code(content(head))
    except (ValueError, subprocess.SubprocessError, UnicodeError):
        return True


def scopes_for_path(path: str, *, code_changed: bool = True) -> set[str]:
    selected = base_scopes_for_path(path, code_changed=code_changed)
    if path in RECIPE_INPUTS and integration_examples_for_path(path):
        selected |= {"python_static", "python_unit"} | GROUPS["paired"]
    return selected


def changed_registry_examples(base: str, head: str) -> set[str]:
    def registry(sha: str) -> dict[str, str]:
        path = "scripts/integration_examples.json"
        entry = git("--literal-pathspecs", "ls-tree", "-z", sha, "--", path)
        if not entry.startswith((b"100644 blob ", b"100755 blob ")):
            raise ValueError("integration registry is not a regular file")
        value: object = json.loads(git("show", f"{sha}:{path}"))
        if not isinstance(value, dict):
            raise ValueError("integration registry must be an object")
        result: dict[str, str] = {}
        for name, convention in cast(dict[object, object], value).items():
            if (
                not isinstance(name, str)
                or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name)
                or not isinstance(convention, str)
                or not convention.strip()
            ):
                raise ValueError("invalid integration registry entry")
            result[name] = convention
        return result

    try:
        before, after = registry(base), registry(head)
        return {name for name, value in after.items() if before.get(name) != value}
    except (ValueError, subprocess.SubprocessError, UnicodeError):
        return set(INTEGRATION_EXAMPLES)


def select(event: str, base: str, head: str) -> dict[str, bool | str | list[str]]:
    selected: set[str] = ALL.copy()
    integration_examples: set[str] = set(INTEGRATION_EXAMPLES)
    paired_snippets_live = True
    full = True
    lint_all = False
    docs_links = False
    file_checks = True
    try:
        if event in {"push", "pull_request"}:
            if not all(re.fullmatch(r"[0-9a-f]{40}", sha) and set(sha) != {"0"} for sha in (base, head)):
                raise ValueError("missing or invalid comparison commit")
            if event == "pull_request":
                base = git("merge-base", base, head).decode().strip()
            # No rename detection: both the old and new paths must contribute coverage.
            paths = git("diff", "--name-only", "--no-renames", "-z", base, head, "--").decode("utf-8").split("\0")
            file_checks = any(paths)
            docs_paths = {path for path in paths if path.startswith("docs/src/")}
            if docs_paths:
                deleted = set(
                    git("diff", "--name-only", "--diff-filter=D", "--no-renames", "-z", base, head, "--")
                    .decode("utf-8")
                    .split("\0")
                )
                # Pre-commit omits deleted files. A surviving changed docs file
                # normally triggers the global link hook; deletion-only diffs cannot.
                docs_links = docs_paths <= deleted
            selected = set()
            integration_examples = set()
            paired_snippets_live = False
            for path in filter(None, paths):
                lint_all |= path in {".pre-commit-config.yaml", "pyproject.toml"} or path.endswith("/pyproject.toml")
                markdown = path == "README.md" or (path.startswith("docs/") and path.endswith((".md", ".mdx")))
                code_changed = changed_code(base, head, path) if markdown else True
                path_scopes = scopes_for_path(path, code_changed=code_changed)
                native_examples = (
                    changed_registry_examples(base, head)
                    if path == "scripts/integration_examples.json"
                    else integration_examples_for_path(path)
                )
                if path == "scripts/integration_examples.json" and not native_examples:
                    path_scopes.discard("paired_live")
                selected |= path_scopes
                paired_snippets_live |= "paired_live" in path_scopes and not native_example_input(path)
                integration_examples |= native_examples
                if path_scopes == ALL:
                    integration_examples |= set(INTEGRATION_EXAMPLES)
                if path.endswith((".py", ".pyi")):
                    selected.add("python_static")
            full = False
    except (ValueError, subprocess.SubprocessError, UnicodeError) as error:
        print(f"Using full CI coverage: {type(error).__name__}", file=sys.stderr)
        selected = ALL.copy()
        integration_examples = set(INTEGRATION_EXAMPLES)
        paired_snippets_live = True
    if event == "schedule":
        # Preserve Python's live-only periodic run; Node keeps its full periodic check.
        selected -= {"python_unit", "python_docs", "cli_contract"}
    return {
        **{name: name in selected for name in sorted(ALL)},
        "full": full,
        "file_checks": full or file_checks,
        "lint_all": full or lint_all or selected == ALL,
        "docs_links": docs_links,
        "base": base,
        "head": head,
        "integration_examples": sorted(integration_examples),
        "paired_snippets_live": paired_snippets_live,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    _ = parser.add_argument("--event", required=True)
    _ = parser.add_argument("--base", default="")
    _ = parser.add_argument("--head", default="")
    _ = parser.add_argument("--output", type=Path)
    _ = parser.add_argument("--summary", type=Path)
    args = parser.parse_args()
    scope = select(args.event, args.base, args.head)
    payload = json.dumps(scope, sort_keys=True)
    print(payload)
    if args.output:
        with args.output.open("a") as output:
            output.write(f"scope={payload}\n")
    if args.summary:
        with args.summary.open("a") as summary:
            summary.write("### Selected CI suites\n\n| Suite | Run |\n| --- | --- |\n")
            for name in ["file_checks", *sorted(ALL)]:
                summary.write(f"| {name} | {'yes' if scope[name] else 'skip'} |\n")
            if scope["full"]:
                summary.write("\nFull coverage: scheduled/manual run or unavailable comparison.\n")


if __name__ == "__main__":
    main()
