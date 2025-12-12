import json
import os
from glob import glob
from io import StringIO
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from notte_eval.agent_handlers.falco import ResultWithCode
from notte_eval.run import load_data, run_tasks


@pytest.mark.use_cli_args
@pytest.mark.timeout(60 * 60)  # fail after 1 hour
def test_benchmark_webvoyager(
    config: str,
) -> None:
    os.makedirs("dist", exist_ok=True)

    with open(config, "r") as f:
        s = f.read().replace("\\n", "\n")

    data = load_data(StringIO(s))

    exp_path = run_tasks(data, dir="dist")

    paths = glob(str(exp_path / "*" / "*" / "results_no_screenshot.json"))
    full_data: list[dict[str, Any]] = []
    for path in paths:
        with open(path, "r") as f:
            full_data.append(json.load(f))

    DISPLAY_HTML_COLUMNS = [
        "task_website",
        "task_id",
        "success",
        "duration_in_s",
        "num_steps",
        "total_input_tokens",
        "total_output_tokens",
        "replay_code",
        "run_id",
    ]
    INDEX_COLS = ["task_website", "task_id", "run_id"]

    df = pd.DataFrame(full_data)

    df["num_steps"] = df["steps"].apply(len)
    df = df[DISPLAY_HTML_COLUMNS].sort_values(by=INDEX_COLS).set_index(INDEX_COLS)

    avg_index = ("Average", "", "")
    df.loc[avg_index] = df.mean(numeric_only=True)
    mask = df.index != avg_index, "success"
    df.loc[mask] = df.loc[mask].apply(lambda val: "✅" if val > 0.5 else "❌")

    with open(Path("dist") / "results.html", "w") as f:
        _ = f.write("# Parameters\n\n```\n")
        json.dump(json.loads((exp_path / "params.json").read_text()), f, indent=2)
        _ = f.write("\n```\n# Results\n\n")
        _ = f.write(
            df.to_html(
                formatters={"replay_code": ResultWithCode.format_html_code},
                escape=False,
                render_links=True,
                float_format="{:.1f}".format,
            )
        )

    assert df.success.all()
