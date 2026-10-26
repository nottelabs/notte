# pyright: basic
"""Find the tasks and probes in `tasks/`, select them, split them across shards, and order the runs.

Every module in `tasks/` can define `TASKS: list[Task]` and `PROBES: list[Probe]`; adding a task or a probe is adding
an entry there (or a new module). A task or probe without a suite gets its module's name as suite.
"""

import importlib
import pkgutil
from dataclasses import dataclass, replace
from itertools import groupby
from types import ModuleType
from typing import Literal

from . import tasks as tasks_package
from .model import Probe, Task

TASK_RUNNERS = ("notte-local", "notte-local-llm", "notte-local-html", "notte-local-scripted")
PROBE_RUNNERS = ("probe-local-jev", "probe-local-llm", "probe-local-scripted")


@dataclass(frozen=True)
class Registry:
    tasks: dict[str, Task]
    probes: dict[str, Probe]


def discover(package: ModuleType = tasks_package) -> Registry:
    tasks: dict[str, Task] = {}
    probes: dict[str, Probe] = {}
    for info in sorted(pkgutil.iter_modules(package.__path__), key=lambda m: m.name):
        module = importlib.import_module(f"{package.__name__}.{info.name}")
        for task in getattr(module, "TASKS", []):
            if task.name in tasks:
                raise ValueError(f"task {task.name!r} is defined twice (again in tasks/{info.name}.py)")
            tasks[task.name] = task if task.suite else replace(task, suite=info.name)
        for probe in getattr(module, "PROBES", []):
            if probe.name in probes:
                raise ValueError(f"probe {probe.name!r} is defined twice (again in tasks/{info.name}.py)")
            probes[probe.name] = probe if probe.suite else replace(probe, suite=info.name)
    return Registry(tasks, probes)


@dataclass(frozen=True)
class Item:
    """The unit of sharding: one task, or the probes of one page (they share a session)."""

    kind: Literal["task", "probes"]
    # the task name, or the probe page URL
    key: str
    # (task name,) or the names of the probes on that page, in registry order
    names: tuple[str, ...]
    suite: str
    fixture: bool

    @property
    def slug(self) -> str:
        return self.names[0]


def select(
    registry: Registry,
    suites: list[str] | None = None,
    tasks: list[str] | None = None,
    probes: list[str] | None = None,
    with_tasks: bool = True,
    with_probes: bool = True,
) -> list[Item]:
    """The items of these suites (all when empty), tasks first then probe pages, in registry order. `tasks` /
    `probes` restrict their kind to these names."""
    known = {t.suite for t in registry.tasks.values()} | {p.suite for p in registry.probes.values()}
    for suite in suites or []:
        if suite not in known:
            raise ValueError(f"unknown suite {suite!r} (known: {', '.join(sorted(known))})")
    for name in tasks or []:
        if name not in registry.tasks:
            raise ValueError(f"unknown task {name!r}")
    for name in probes or []:
        if name not in registry.probes:
            raise ValueError(f"unknown probe {name!r}")
    items: list[Item] = []
    if with_tasks:
        for task in registry.tasks.values():
            if (not suites or task.suite in suites) and (not tasks or task.name in tasks):
                items.append(Item("task", task.name, (task.name,), task.suite, task.fixture))
    if with_probes:
        pages: dict[str, list[Probe]] = {}
        for probe in registry.probes.values():
            if (not suites or probe.suite in suites) and (not probes or probe.name in probes):
                pages.setdefault(probe.url, []).append(probe)
        for url, group in pages.items():
            items.append(Item("probes", url, tuple(p.name for p in group), group[0].suite, group[0].fixture))
    return items


def parse_shard(spec: str) -> tuple[int, int]:
    """`i/n` (1-based) -> (i, n)."""
    index, _, count = spec.partition("/")
    i, n = int(index), int(count)
    if not 1 <= i <= n:
        raise ValueError(f"shard {spec!r}: expected i/n with 1 <= i <= n")
    return i, n


def shard(items: list[Item], index: int, count: int) -> list[Item]:
    """Every `count`-th item from `index` (1-based): deterministic, and each suite spread evenly over the shards."""
    return items[index - 1 :: count]


@dataclass(frozen=True)
class Job:
    version: str
    runner: str
    item: Item
    repeat: int

    @property
    def file(self) -> str:
        """The run file, relative to the output directory."""
        return f"{self.version}/{self.runner}__{self.item.slug}__{self.repeat}.json"


def _cost_class(item: Item) -> int:
    # longest first, so the slowest runs don't start last: public tasks, probe pages, fixture tasks
    if item.kind == "probes":
        return 1
    return 2 if item.fixture else 0


def plan(items: list[Item], runners: list[str], versions: list[str], repeats: int) -> list[Job]:
    """The runs in start order. The versions of one item and runner are adjacent, so they see the same site and
    machine conditions; which one goes first alternates from item to item and from repeat to repeat."""
    ordered = sorted(items, key=_cost_class)
    jobs: list[Job] = []
    for repeat in range(1, repeats + 1):
        for k, item in enumerate(ordered):
            kinds = PROBE_RUNNERS if item.kind == "probes" else TASK_RUNNERS
            order = versions if (k + repeat) % 2 else versions[::-1]
            for runner in runners:
                if runner in kinds:
                    jobs.extend(Job(version, runner, item, repeat) for version in order)
    return jobs


def pairs(jobs: list[Job]) -> list[list[Job]]:
    """The versions of one item, runner and repeat, in plan order: `bench.py` runs each group one job after the
    other, so base and head of a task never hit the site at once."""
    return [list(group) for _, group in groupby(jobs, key=lambda job: (job.runner, job.item, job.repeat))]
