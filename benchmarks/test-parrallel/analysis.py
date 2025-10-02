import csv
import html
import json
from datetime import datetime
from pathlib import Path
from typing import Any


def generate_base_csv(csv_path: str) -> None:
    total_output_data: list[dict[str, Any]] = []

    field_names = [
        "website",
        "task_id",
        "evaluation",
        "agent_success",
        "exec_time_secs",
        "num_steps",
        "total_input_tokens",
        "total_output_tokens",
    ]

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
        website = task["id"].split("--")[1]

        response = raw_data["response"]
        eval = raw_data["eval"]

        output_data["website"] = website
        output_data["task_id"] = task["id"]
        output_data["evaluation"] = eval["eval"]
        output_data["agent_success"] = response["success"]
        output_data["exec_time_secs"] = round(response["duration_in_s"], 2)
        output_data["num_steps"] = response["n_steps"]
        output_data["total_input_tokens"] = response["input_tokens"]
        output_data["total_output_tokens"] = response["output_tokens"]

        total_output_data.append(output_data)

    total_output_data.sort(
        key=lambda item: (item["website"], item["task_id"])
    )  # pytest: ignore[reportUnknownLambdaType, reportUnknownMemberType]

    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=field_names)
        writer.writeheader()
        writer.writerows(total_output_data)


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

    output_data_path = f"raw_output_data/base_output_data_{timestamp}.csv"
    output_md_path = f"raw_output_data/output_table_{timestamp}.md"
    output_html_path = f"raw_output_data/output_table_{timestamp}.html"

    generate_base_csv(output_data_path)

    md_table = csv_to_markdown_string(output_data_path)

    with open(output_md_path, "w") as f:
        _ = f.write("# WebVoyager Results\n\n" + md_table + "\n\n")

    # csv_to_markdown(output_data_path, output_md_path)
    # csv_to_html(output_data_path, output_html_path)
