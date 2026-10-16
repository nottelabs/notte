# DOM and action-id characterization

These tests pin the behavior of `v2/main` at `a20a60ca`. They deliberately preserve
current naming and action-type quirks rather than defining new behavior.

Seven synthetic pages cover native forms and naming, disabled controls, nested
button/link text, an icon button, custom ARIA widgets, both kinds of open dialog,
two levels of same-origin `srcdoc` iframes, nested open shadow roots, and inline
JavaScript that creates controls. Fixtures live outside `tests/data` because the
existing golden loader recursively discovers HTML there and removes scripts and
iframes. All browser requests are fulfilled locally or aborted.

Each synthetic snapshot stores the exact observation description (with an added
file-ending newline), the complete unfiltered action `model_dump()` including all
selectors, and the public `description`, `category`, and `param` fields separately.
The latter matters because Pydantic can exclude those fields from serialization.
`tests/golden/test_full_actions.py` adds the same action records as `actions.json`
beside all 11 existing saved-page snapshots; their old files are unchanged.

The hash components of `notte_selector` use Python's process-randomized `hash()`.
Snapshot capture therefore starts a subprocess with `PYTHONHASHSEED=0`; it does
not remove, replace, or normalize any dumped field. Each synthetic page is
observed three times in two fresh sessions in each of two independent processes
(12 observations per fixture). All results must agree, with action order intact.
The normal offline pytest command requires no hash-seed setting.

The 42 successful round trips send only an observed action id and execution
parameters to `aexecute`, never the observed selector. Literal id-to-target cases
and independently installed DOM event/state probes ensure only the intended
control receives the action and other controls keep their state. They cover all
native controls, the custom button/checkbox/combobox/options/menuitem/tab, both
iframe depths, both shadow depths, generated controls, and controls inside and
outside both dialogs. ARIA options are clicked by id; native/custom comboboxes
are selected by id. The listbox and menu containers are pinned in snapshots but
are not treated as editable/independent controls. Each case checks stable ids
across two unchanged observations. Two additional tests cover unknown ids and
removed elements with both cached and refreshed observations.

Run without updating:

```sh
uv run --no-sync pytest tests/golden tests/characterization
```

Only when intentionally changing the baseline, regenerate the new files:

```sh
NOTTE_UPDATE_GOLDEN=1 uv run --no-sync pytest tests/characterization tests/golden/test_full_actions.py
```

To compare another branch, copy only the files added by this tests commit into a
scratch worktree, set up its own environment, and run the first command without
`NOTTE_UPDATE_GOLDEN`. Captures in pytest's temporary directories include the
fixture name, exact description and full action JSON for complete field-by-field
diffs even when the description assertion fails first. Never regenerate frozen
snapshots on a comparison branch.
