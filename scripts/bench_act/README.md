# act benchmark

A dev benchmark of `session.act()`, `choose()` and `check()`, and of the observe they read. It is not shipped.

- A **task** is a goal on a start page. One run acts until the runner stops (DONE, BLOCKED, stale, no progress) or
  hits the task's step cap. Success is checked on the final page (URL, DOM, submitted data), whatever the runner
  claims.
- A **probe** is a `choose()` or `check()` question with a known answer. The probes of one page share a session.

## Layout

| path | what |
|---|---|
| `tasks/*.py` | the tasks and probes. Each module defines `TASKS` and/or `PROBES`; suite = module name unless set |
| `fixtures/` | local pages, served on a free port. `{fixtures}` in a URL points to them |
| `model.py` | `Task`, `Probe`, and the helpers success checks share |
| `registry.py` | discovery, `--suites` selection, `--shard i/n`, run order |
| `bench.py` | runs the plan, N runs at once, one process per run (`worker.py`) |
| `runners.py` | the runners on a local `NotteSession`, recording every model call |
| `rules.py` | site misses and the pass/fail rules |
| `report.py` | merges run files (one or more directories) into tables or the CI summary |

To add a task or probe, add an entry to a module in `tasks/`, or add a new module. The fields are:

```python
Task(name, url, goal, check, tags=(), max_steps=15, pre_js=None, suite="")
Probe(name, url, question, options, answer, suite="")
```

`check(final, run) -> bool` gets the final page (`runners.PROBE_JS`: url, text, inputs, tables, frames, ...) and the
run record (steps, decisions, `pre`). Names must be unique across modules.

## Running

Needs `OPENROUTER_API_KEY` (Jev and the LLM decider go through OpenRouter).

```bash
export DISABLE_TELEMETRY=true
# everything, once, 6 runs at once
uv run --no-sync python scripts/bench_act/bench.py --concurrency 6 --out /tmp/act-bench
# some tasks, Jev and the LLM decider, 3 times
uv run --no-sync python scripts/bench_act/bench.py --runners notte-local,notte-local-llm --tasks search,hn \
    --repeats 3 --out /tmp/act-bench
# base against head: two checkouts, each synced with `uv sync --all-extras`
python scripts/bench_act/bench.py --tree base=../notte-base --tree head=. --suites real --out /tmp/act-bench-ab
uv run --no-sync python scripts/bench_act/report.py /tmp/act-bench [--failures]
uv run --no-sync python scripts/bench_act/report.py /tmp/act-bench-ab --summary summary.md --check
```

- Runners: `notte-local` (Jev), `notte-local-llm`, `notte-local-html` (HTML labels), `probe-local-jev`,
  `probe-local-llm`. The default is `notte-local,probe-local-jev`.
- `--concurrency` defaults to half the CPU count.
- Each run is its own process with its own browser and session. The fixture server is shared.
- The versions of one task run back to back, so they see the same site and machine conditions. Which version
  goes first alternates.
- Run files go to `OUT/<version>/<runner>__<task or first probe>__<repeat>.json`, worker logs to `OUT/_logs/`, and
  the plan and timings (wall time, load average) to `OUT/_meta/`.
- An existing run file is not run again, so an interrupted run can be resumed.

## CI

`.github/workflows/act-bench.yml` runs the benchmark when:

- a PR gets the `act-bench` label (and on later pushes while it has the label);
- a PR changes `notte_browser/js`, `notte_browser/dom`, `notte_core/act`, `notte_llm/act.py` or this directory;
- someone starts it by hand (`workflow_dispatch`, from the default branch).

Each shard job checks out head and base (on PRs, the merge base), syncs both, and runs its share of the tasks with
both versions interleaved. A report job merges the shards, writes the job summary and applies the rules in
`rules.py`:

- fixture tasks and fixture probes must always pass;
- public sites fail only on a clear drop against base;
- site misses (blocks, CAPTCHAs, redirects off the site) are left out.

It needs the `OPENROUTER_API_KEY` repository secret. Fork PRs get no secrets and skip; a same-repo run without
the secret fails.
