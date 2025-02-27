import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Literal

from loguru import logger

WEBVOYAGER_DATA_PATH = Path(__file__).parent / "data"


@dataclass
class WebVoyagerAnswer:
    type: Literal["possible", "golden"]
    answer: str

    def __post_init__(self):
        if self.type not in ["possible", "golden"]:
            raise ValueError(f"Invalid answer type: {self.type}")


@dataclass
class WebVoyagerTask:
    name: str
    id: int
    question: str
    ref_answers: list[WebVoyagerAnswer]
    url: str
    screenshot: str | None = None


class WebVoyagerSubset(Enum):
    Full = "full"
    Short = "short"
    Simple = "simple"
    Single = "single"

    def path(self) -> str:
        match self:
            case WebVoyagerSubset.Full:
                return "WebVoyager_data.jsonl"
            case WebVoyagerSubset.Short:
                return "WebVoyager_data_short.jsonl"
            case WebVoyagerSubset.Simple:
                return "WebVoyager_data_simple.jsonl"
            case WebVoyagerSubset.Single:
                return "WebVoyager_data_single.jsonl"


def load_webvoyager_data(
    subset: WebVoyagerSubset = WebVoyagerSubset.Full,
    exclude_impossible: bool = False,
) -> list[WebVoyagerTask]:
    with open(WEBVOYAGER_DATA_PATH / "reference_answer.json", "r") as f:
        answers = json.load(f)

    excluded_ids: set[str] = set()
    if exclude_impossible:
        with open(WEBVOYAGER_DATA_PATH / "WebVoyager_excluded_data.jsonl", "r") as f:
            excluded_tasks = [json.loads(line) for line in f]
            excluded_ids = {task["task_id"] for task in excluded_tasks}

    tasks: list[WebVoyagerTask] = []
    with open(WEBVOYAGER_DATA_PATH / subset.path(), "r") as f:
        for line in f:
            data = json.loads(line)
            if data["id"] in excluded_ids:
                logger.warning(f"Excluding task {data['id']} because it is in the excluded list")
                continue
            raw_ids = data["id"].split("--")
            website_id, task_id = raw_ids[0], int(raw_ids[1])
            task_answer = answers[website_id]["answers"][task_id]
            task_ref_answers = [WebVoyagerAnswer(type=task_answer["type"], answer=task_answer["ans"])]
            tasks.append(
                WebVoyagerTask(
                    name=data["web_name"],
                    id=task_id,
                    question=data["ques"],
                    ref_answers=task_ref_answers,
                    url=data["web"],
                    screenshot=data.get("screenshot"),
                )
            )
    return tasks
