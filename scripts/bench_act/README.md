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
Task(name, url, goal, check, tags=(), max_steps=15, pre_js=None, suite="", final_js=None)
Probe(name, url, question, options, answer, suite="", tags=())
```

`check(final, run) -> bool` gets the final page (`runners.PROBE_JS`: url, text, inputs, tables, frames, ...) and the
run record (steps, decisions, `pre`). `final_js` (a JS expression returning a JSON string) adds what the page probe
does not read as `final["extra"]`. Names must be unique across modules. Each module ends with `ci_tier(TASKS, core=...)`
and `ci_tier(PROBES, core=...)`, which tags every entry with its CI tier (below); a new entry is `ci-extended` unless
its module lists it in `core`.

## CI tiers

| tier | what | runs | size |
|---|---|---|---|
| `ci-core` | local pages, and very stable public demos and docs (the-internet, toscrape, selenium.dev, TodoMVC, UI Testing Playground, W3C APG, Wikipedia, docs.python.org, DataTables, scrapethissite.com) | every PR that changes observe or act | 61 tasks, 88 probes on 59 pages |
| `ci-extended` | third-party sites (Google, booking.com, IKEA, GitHub, shops, news, cookie platforms, editors' sites), pages with ads, known flakes, tasks that fail until a bug is fixed | on demand (`tags: ci-extended` or `all`) | 50 tasks, 39 probes on 29 pages |

Why an entry is extended is written next to its module's `ci_tier` call. `--tags ci-core` selects a tier locally.
Measured locally (Jev, one version, concurrency 6, on a loaded shared machine): the core tier is 121 runs, 1,838
run-seconds, 320 s wall. Base and head double the runs. On CI, at concurrency 6 in one job that is about 10 minutes plus
about a minute of setup; with the default 4 shards at concurrency 4, about 5 minutes. The extended tier is about 1,100
run-seconds per version: 7 to 8 minutes at concurrency 6, about 4 with 4 shards. A CI runner ran the model-free scripted
runs about twice as fast as that machine, so these are upper bounds.

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

- `--tags ci-core` (or `ci-extended`) runs one CI tier; the default is everything.
- Runners: `notte-local` (Jev), `notte-local-llm`, `notte-local-html` (HTML labels), `probe-local-jev`,
  `probe-local-llm`. The default is `notte-local,probe-local-jev`. `notte-local-scripted` and
  `probe-local-scripted` use no model and no key (scroll, then DONE): they time the browser side and the CI
  setup, and are not judged.
- `--concurrency` defaults to half the CPU count.
- Each run is its own process with its own browser and session. The fixture server is shared.
- The versions of one task run back to back (one after the other, never at once), so they see the same site and
  machine conditions. Which version goes first alternates. `--tree` takes `base=` and `head=` only.
- Travel tasks count their dates from `--today` (default: today): a Friday 4 to 5 weeks ahead (`model.trip_dates`).
  New tasks with dates should use it too, so they never ask for a past day.
- Run files go to `OUT/<version>/<runner>__<task or first probe>__<repeat>.json`, worker logs to `OUT/_logs/`, and
  the plan and timings (wall time, load average) to `OUT/_meta/`.
- An existing run file of the same commit is not run again, so an interrupted run can be resumed.

## CI

`.github/workflows/act-bench.yml` runs the benchmark when:

- a PR gets the `act-bench` or `act-bench-all` label (and on later pushes while it has the label);
- a PR changes `notte_browser/js`, `notte_browser/dom`, `notte_core/act`, `notte_llm/act.py` or this directory;
- someone starts it by hand (`workflow_dispatch`, from the default branch).

PRs run the `ci-core` tier, or every tier with the `act-bench-all` label; a manual run picks its tier with the
`tags` input (`ci-core`, `ci-extended` or `all`).

Each shard job checks out head and base (on PRs, the merge base), syncs both, and runs its share of the tasks with
both versions interleaved. A report job merges the shards, writes the job summary and applies the rules in
`rules.py`:

- the rules judge the Jev runners; the LLM and scripted runners are reported only;
- fixture tasks and fixture probes must always pass;
- public sites fail only on a clear drop against base;
- site misses (blocks, CAPTCHAs, redirects off the site) are left out;
- infra misses (the decider could not be reached, timed out or answered 5xx) are counted apart, and the run fails
  when they exceed 5% of the runs. The harness never retries a run.

It needs the `OPENROUTER_API_KEY` repository secret. Fork PRs get no secrets and skip; a same-repo run without
the secret fails.
