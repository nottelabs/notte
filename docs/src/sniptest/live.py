"""Require a behavior contract for every executable pair, not just successful exit."""

import json
from pathlib import Path

from catalog import execution_backlog

# These original pairs have dedicated assertions in docs-snippets.integration.test.ts.
DEDICATED_CASES = {
    "client/index.ts",
    "quickstart/set_api_key.ts",
    "quickstart/cdp_session.ts",
    "functions/invoke_sdk.ts",
    "functions/invocations/async_create_start.ts",
    "sessions/lifecycle/context_manager.ts",
}


def check_live_contracts(testers: Path, contracts: dict, dedicated: set[str] | None = None) -> list[str]:
    dedicated = DEDICATED_CASES if dedicated is None else dedicated
    pending = execution_backlog(testers)
    executable = {str(path.relative_to(testers)) for path in testers.rglob("*.ts")} - set(pending)
    errors = []
    for name in sorted(executable - set(contracts) - dedicated):
        errors.append(f"Executable pair needs a behavior contract: {name}")
    for name in sorted(set(contracts) - executable):
        errors.append(f"Stale or non-executable behavior contract: {name}")
    for name in sorted(executable):
        python = str(Path(name).with_suffix(".py"))
        if not (testers / python).is_file() or python in pending:
            errors.append(f"Executable pair needs an executable Python counterpart: {name}")
    for name, contract in contracts.items():
        if not isinstance(contract, dict) or not isinstance(contract.get("expected"), dict) or not contract["expected"]:
            errors.append(f"Behavior contract needs nonempty expected output: {name}")
            continue
        if set(contract) - {"expected", "closedSession", "logContains"}:
            errors.append(f"Unknown behavior contract fields: {name}")
        if "closedSession" in contract and not isinstance(contract["closedSession"], bool):
            errors.append(f"closedSession must be boolean: {name}")
        if "logContains" in contract and (not isinstance(contract["logContains"], str) or not contract["logContains"]):
            errors.append(f"logContains must be a nonempty string: {name}")
    return errors


if __name__ == "__main__":
    directory = Path(__file__).resolve().parent
    contracts = json.loads((directory / "live-examples.json").read_text())
    errors = check_live_contracts(directory.parent / "testers", contracts)
    if errors:
        raise SystemExit("\n".join(errors))
    print(f"Live behavior coverage OK: {len(contracts)} output contracts plus {len(DEDICATED_CASES)} dedicated cases")
