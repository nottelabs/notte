import csv
import html
import json
from datetime import datetime
from pathlib import Path
from typing import Any


def generate_base_csv(csv_path: str, config_path: str) -> None:
    total_output_data: list[dict[str, Any]] = []

    field_names = [
        "website",
        "task_id",
        "eval_success",
        "agent_success",
        "exec_time_secs",
        "num_steps",
        "total_input_tokens",
        "total_output_tokens",
    ]

    tasks_list: list[str] = []
    tasks_completed: list[str] = []

    with open(config_path, "r") as f:
        for line in f.readlines():
            conf_json = json.loads(line)
            tasks_list.append(conf_json["id"])

    base_data_dir = "raw_output_data/"
    base_data_dir_path = Path(base_data_dir)

    tasks = [entry.name for entry in base_data_dir_path.iterdir() if entry.is_dir()]

    for dir in tasks:
        raw_data_dir = base_data_dir + dir + "/"
        raw_data_path = raw_data_dir + "output.json"

        if not Path(raw_data_path).exists():
            continue

        with open(raw_data_path, "r") as f:
            raw_data = json.load(f)

        output_data: dict[str, Any] = {}

        task = raw_data["task"]
        tasks_completed.append(task["id"])
        website = task["id"].split("--")[1]

        response = raw_data["response"]
        eval = raw_data["eval"]

        eval_res: str | bool = eval["eval"]

        if eval_res == "success":
            eval_res = True
        elif eval_res == "failure":
            eval_res = False

        output_data["website"] = website
        output_data["task_id"] = task["id"]
        output_data["eval_success"] = eval_res
        output_data["agent_success"] = response["success"]
        output_data["exec_time_secs"] = round(response["duration_in_s"], 2)
        output_data["num_steps"] = response["n_steps"]
        output_data["total_input_tokens"] = response["input_tokens"]
        output_data["total_output_tokens"] = response["output_tokens"]

        total_output_data.append(output_data)

    not_completed = list(set(tasks_list) - set(tasks_completed))

    total_output_data.sort(
        key=lambda item: (item["website"], item["task_id"])
    )  # pytest: ignore[reportUnknownLambdaType, reportUnknownMemberType]

    for task in not_completed:
        output_data_incomplete: dict[str, Any] = {}
        output_data_incomplete["website"] = task.split("--")[1]
        output_data_incomplete["task_id"] = task
        output_data_incomplete["eval_success"] = "something went wrong"
        output_data_incomplete["agent_success"] = False

        total_output_data.append(output_data_incomplete)

    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=field_names)
        writer.writeheader()
        writer.writerows(total_output_data)


def generate_analysis_csv(base_csv_path: str, csv_path: str) -> None:
    field_names = [
        "eval_success_rate",
        "agent_success_rate",
        "avg_num_steps",
        "avg_time_per_step",
        "avg_in_tokens_per_step",
        "avg_out_tokens_per_step",
    ]

    with open(base_csv_path, "r", newline="") as f:
        reader = csv.DictReader(f)
        base_data = list(reader)

    data: dict[str, Any] = {}
    output_data: list[dict[str, Any]] = []

    count = 0

    eval_successes = 0
    agent_successes = 0

    total_n_steps = 0
    total_exec_time = 0
    total_in_tokens = 0
    total_out_tokens = 0

    for task in base_data:
        count += 1

        if task["eval_success"] == "True":
            eval_successes += 1

        if task["agent_success"] == "True":
            agent_successes += 1

        if task["num_steps"] != "":
            total_n_steps += int(task["num_steps"])
            total_exec_time += float(task["exec_time_secs"])
            total_in_tokens += int(task["total_input_tokens"])
            total_out_tokens += int(task["total_output_tokens"])

    data["eval_success_rate"] = round(eval_successes / count, 2)
    data["agent_success_rate"] = round(agent_successes / count, 2)
    data["avg_num_steps"] = round(total_n_steps / count, 2)
    data["avg_time_per_step"] = round(total_exec_time / total_n_steps, 2)
    data["avg_in_tokens_per_step"] = round(total_in_tokens / total_n_steps, 2)
    data["avg_out_tokens_per_step"] = round(total_out_tokens / total_n_steps, 2)

    output_data.append(data)

    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=field_names)
        writer.writeheader()
        writer.writerows(output_data)


def csv_to_markdown(csv_path: str, md_path: str) -> None:
    with open(csv_path, newline="") as csvfile:
        reader = list(csv.reader(csvfile))

    if not reader:
        raise ValueError("CSV is empty")

    headers = reader[0]
    rows = reader[1:]

    with open(md_path, "w") as mdfile:
        # Write header
        _ = mdfile.write("| " + " | ".join(headers) + " |\n")
        # Write separator
        _ = mdfile.write("|" + "|".join([" --- " for _ in headers]) + "|\n")
        # Write data rows
        for row in rows:
            _ = mdfile.write("| " + " | ".join(row) + " |\n")


def csv_to_markdown_string(csv_path: str) -> str:
    with open(csv_path, newline="") as csvfile:
        reader = list(csv.reader(csvfile))

    if not reader:
        raise ValueError("CSV is empty")

    headers = reader[0]
    rows = reader[1:]

    lines: list[str] = []
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("|" + "|".join([" --- " for _ in headers]) + "|")
    for row in rows:
        row = ["✅" if x == "True" else "❌" if x == "False" else x for x in row]
        lines.append("| " + " | ".join(row) + " |")

    return "\n".join(lines)


def csv_to_markdown_string_no_header(csv_path: str) -> str:
    with open(csv_path, newline="") as csvfile:
        reader = list(csv.reader(csvfile))

    if not reader:
        raise ValueError("CSV is empty")

    rows = reader[1:]

    lines: list[str] = []
    for row in rows:
        row = [f"**{s}**" for s in row]
        lines.append("| " + " | ".join(row) + " |")

    return "\n".join(lines)


def csv_to_html(csv_path: str, html_path: str) -> None:
    with open(csv_path, newline="") as csvfile:
        reader = list(csv.reader(csvfile))

    if not reader:
        raise ValueError("CSV is empty")

    headers = reader[0]
    rows = reader[1:]

    with open(html_path, "w") as f:
        _ = f.write("<!DOCTYPE html>\n<html>\n<head>\n")
        _ = f.write("<meta charset='UTF-8'>\n<title>CSV Table</title>\n")
        _ = f.write(
            "<style>table { border-collapse: collapse; } th, td { border: 1px solid #ccc; padding: 8px; }</style>\n"
        )
        _ = f.write("</head>\n<body>\n<table>\n")

        # Write header
        _ = f.write("<thead><tr>")
        for header in headers:
            _ = f.write(f"<th>{html.escape(header)}</th>")
        _ = f.write("</tr></thead>\n")

        # Write data rows
        _ = f.write("<tbody>\n")
        for row in rows:
            _ = f.write("<tr>")
            for cell in row:
                _ = f.write(f"<td>{html.escape(cell)}</td>")
            _ = f.write("</tr>\n")
        _ = f.write("</tbody>\n")

        _ = f.write("</table>\n</body>\n</html>")


def csv_to_html_string(csv_path: str) -> str:
    with open(csv_path, newline="") as csvfile:
        reader = list(csv.reader(csvfile))

    if not reader:
        raise ValueError("CSV is empty")

    headers = reader[0]
    rows = reader[1:]

    lines: list[str] = []
    lines.append("<table>")
    lines.append("<thead><tr>")
    for header in headers:
        lines.append(f"<th>{html.escape(header)}</th>")
    lines.append("</tr></thead>")

    lines.append("<tbody>")
    for row in rows:
        lines.append("<tr>")
        for cell in row:
            lines.append(f"<td>{html.escape(cell)}</td>")
        lines.append("</tr>")
    lines.append("</tbody>")
    lines.append("</table>")

    return "\n".join(lines)


if __name__ == "__main__":
    timestamp: str = datetime.now().strftime("%Y%m%d_%H%M")

    config_path = "benchmarks/webvoyager/data/webvoyager_simple.jsonl"
    output_data_path = f"raw_output_data/base_output_data_{timestamp}.csv"
    output_analysis_path = f"raw_output_data/agg_output_data_{timestamp}.csv"
    output_md_path = f"raw_output_data/output_table_{timestamp}.md"
    output_html_path = f"raw_output_data/output_table_{timestamp}.html"

    generate_base_csv(output_data_path, config_path)
    generate_analysis_csv(output_data_path, output_analysis_path)

    md_table = csv_to_markdown_string(output_data_path)
    md_table_2 = csv_to_markdown_string(output_analysis_path)

    with open(output_md_path, "w") as f:
        _ = f.write("# Overall\n\n" + md_table_2 + "\n\n")
        _ = f.write("# WebVoyager Results\n\n" + md_table + "\n\n")

    # csv_to_markdown(output_data_path, output_md_path)
    # csv_to_html(output_data_path, output_html_path)
