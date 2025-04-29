import json

import pandas as pd

tasks = pd.read_json("webvoyager.jsonl", lines=True)  # type: ignore

with open("answers.json", "r") as f:
    answers = json.load(f)

series = pd.DataFrame(
    [
        {"id": f"{key}--{answer['id']}", "answer": answer["ans"]}
        for key, values in answers.items()
        for answer in values["answers"]
    ]
)

merged = tasks.merge(series, how="inner", on="id").rename(
    columns={"web_name": "website_name", "ques": "question", "web": "url"}
)
merged["id"] = "webvoyager--" + merged["id"]

merged.to_json("output.jsonl", orient="records", lines=True)  # type: ignore
