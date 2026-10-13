# Validation on 2026-10-13

Baseline: `v2/main` at `a20a60ca0642891942d9eaf279d2f1bf9a65e586`.
Tests and frozen snapshots committed as `239a4952` before copying them to either
comparison worktree. Python 3.11.13, macOS, each worktree set up with
`uvx uv@latest sync --all-packages --all-extras`.

## Main

- `uv run --no-sync pre-commit run --files <all added files>`: passed, including
  pinned Ruff and basedpyright with zero errors and zero warnings.
- `uv run --no-sync pytest -q tests/golden tests/characterization`: 73 passed.
  This includes all 11 unchanged observe/scrape golden cases, 11 new full-action
  saved-page cases, and 51 synthetic characterization cases.
- Offline gate before additions: 1,146 passed, 4 skipped.
- Offline gate after additions: 1,208 passed, 4 skipped.

Both coverage measurements used the same gate and sources:

```sh
env -u NOTTE_API_KEY uv run --no-sync pytest -q -n logical tests \
  -m "not staging and not live" \
  --ignore=tests/examples/test_examples.py \
  --ignore=tests/examples/test_readme.py \
  --cov=packages/notte-browser/src/notte_browser \
  --cov=packages/notte-core/src/notte_core \
  --cov-report=term-missing:skip-covered
```

Line coverage before → after (covered lines / statements):

- `notte_browser/dom/locate.py`: 29.09% → 45.45% (32/110 → 50/110).
- `notte_browser/resolution.py`: 91.30% → 95.65% (63/69 → 66/69).
- `notte_browser/tagging/type.py`: 68.60% → 73.26% (59/86 → 63/86).
- `notte_core/browser/dom_tree.py`: 94.93% → 94.93% (281/296 → 281/296).
- `notte_browser/dom/builder.py`: 94.56% → 94.56% (139/147 → 139/147).
- `notte_browser/dom/csspaths.py`: 84.85% → 84.85% (56/66 → 56/66).
- `notte_browser/dom/parsing.py`: 97.64% → 97.64% (124/127 → 124/127).
- `notte_browser/rendering/interaction_only.py`: 93.44% → 93.44% (57/61 → 57/61).
- `notte_browser/tagging/action_space.py`: 93.33% → 93.33% (14/15 → 14/15).

The remaining `locate.py` misses include file-upload discovery and error/fallback
branches outside these click/fill/select/check fixtures. These tests increase
behavioral coverage; they do not establish complete coverage of DOM processing.

## Frozen tests on the comparison branches

Only the new test files, fixtures, and snapshots were copied to detached scratch
worktrees. Each used its own virtual environment. No snapshots were regenerated,
and neither branch nor its PR was changed.

Command in each scratch worktree:

```sh
env -u NOTTE_API_KEY -u NOTTE_UPDATE_GOLDEN uv run --no-sync pytest -q -n 4 \
  tests/golden tests/characterization
```

- #39 / `v2/v2-dom-python-simplify-3` at
  `f1914e8a26b40a0ce5348b3b5fc996c276feb760`: **73 passed; differences: none**.
- #32 / `v2/v2-act-observe` at
  `e8b6c9af9d813730bef6ee626ef14942d91d88eb`: **73 passed; differences: none**.
  Its new DomNode state fields do not appear in the observed action dumps, so
  there are no added action fields to exempt from comparison.

An additional recursive comparison of the captured outputs against the committed
baseline checked all 18 pages and 231 action records on each branch: zero field,
value, selector, action-order, or description differences. The unchanged scrape
snapshots and all 42 successful id-execution round trips also passed on both.
