"""Accuracy and latency of the accessible names `buildDomNode.js` computes; run with `uv run python`.

    uv run python scripts/benchmark_accessible_names.py accuracy [--fixtures DIR] [--public]
    uv run python scripts/benchmark_accessible_names.py latency [--fixtures DIR] [--public] [-n 10] [--same-page] [--repeat N]

Pages: the golden pages of `tests/data` (served from disk without scripts and iframes, as the golden
tests do), the `*.html` pages of `--fixtures` (served from disk, scripts kept) and, with `--public`,
a few public sites.

`accuracy` compares, for every interaction element, the name computed in `buildDomNode.js` with the
one Chromium computes (`element.computedName`, behind `--enable-blink-features=ComputedAccessibilityInfo`),
and checks on the elements both can join that `computedName` agrees with `Accessibility.getFullAXTree`.

`latency` alternates observes between variants, each in its own browser (Chromium keeps its
accessibility tree up to date once it is built, which would slow down the other variants' pages):
- `off`: no names (the script's name computation is disabled)
- `js`: the names of `buildDomNode.js`
- `cdp`: `off`, then the names of `Accessibility.getFullAXTree`, joined to the DOM nodes by XPath
  through `DOM.getDocument` (main frame only)
- `computed`: `element.computedName` read in the script instead of the JS computation

With `--same-page`, `off` and `js` alternate in one browser on the same page instead: public sites
serve each browser a slightly different page, which hides a difference of a few milliseconds.
`--repeat N` makes `js` compute every name N times, so the cost of one computation is the `js` / `off`
difference divided by N (the repeats find the computed styles cached by the first one).
"""

import argparse
import asyncio
import json
import statistics
import time
from collections import Counter
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from lxml import html as lxml_html
from notte_browser import window as window_module
from notte_browser.dom import parsing
from notte_browser.driver import CDPSession, Page
from notte_core.dom_tree import DomNode
from patchright.async_api import Route

import notte

ROOT = Path(__file__).resolve().parent.parent
GOLDEN_DIR = ROOT / "tests" / "data"
GOLDEN_URL = "http://golden.test/"
FIXTURES_URL = "http://fixtures.test/"
PUBLIC_PAGES = {
    "wikipedia": "https://en.wikipedia.org/wiki/Ada_Lovelace",
    "github": "https://github.com/microsoft/playwright",
    "ecommerce": "https://www.ikea.com/us/en/cat/chairs-fu002/",
    "news": "https://www.aljazeera.com/",
    "docs": "https://docs.python.org/3/library/stdtypes.html",
    "hackernews": "https://news.ycombinator.com/",
}
CHROME_FLAG = "--enable-blink-features=ComputedAccessibilityInfo"
CHROME_ARGS = ["--disable-dev-shm-usage", "--no-sandbox", "--mute-audio", "--no-first-run", CHROME_FLAG]
VARIANTS = ("off", "js", "cdp", "computed")
# the variants that do not build Chromium's accessibility tree, which can share a page
SAME_PAGE_VARIANTS = ("off", "js")
NAME_FUNCTION = "function getAccessibleName(element) {"
NAME_CALL = "const accessibleName = getAccessibleName(node);"
MAX_NAME_LENGTH = 200


def variant_script(variant: str, repeat: int = 1) -> str:
    script = parsing.DOM_TREE_JS
    assert NAME_FUNCTION in script and NAME_CALL in script, "buildDomNode.js no longer calls getAccessibleName"
    if variant in ("off", "cdp"):
        return script.replace(NAME_FUNCTION, NAME_FUNCTION + "\n\t\treturn undefined;", 1)
    if variant == "computed":
        body = 'const computedName = (element.computedName || "").replace(/\\s+/g, " ").trim();'
        body += "\n\t\treturn computedName ? computedName.slice(0, MAX_NAME_LENGTH) : undefined;"
        return script.replace(NAME_FUNCTION, f"{NAME_FUNCTION}\n\t\t{body}", 1)
    if repeat > 1:
        loop = f"let accessibleName; for (let i = 0; i < {repeat}; i++) accessibleName = getAccessibleName(node);"
        return script.replace(NAME_CALL, loop, 1)
    return script


# ---------------------------------------------------------------------------------------------
# pages


@dataclass(frozen=True)
class PageSpec:
    group: str
    name: str
    url: str


def golden_html(path: Path) -> str:
    document: Any = lxml_html.document_fromstring(path.read_text())  # pyright: ignore[reportUnknownMemberType]
    for element in cast(list[Any], document.xpath("//script | //iframe")):
        element.drop_tree()
    return lxml_html.tostring(document, encoding="unicode", doctype="<!DOCTYPE html>")


def make_router(fixtures: Path | None) -> Callable[[Route], Awaitable[None]]:
    async def route(route: Route) -> None:
        url = route.request.url
        if url.startswith(GOLDEN_URL):
            path = (GOLDEN_DIR / url.removeprefix(GOLDEN_URL).split("?")[0].lstrip("/")).resolve()
            if route.request.resource_type == "document" and path.is_relative_to(GOLDEN_DIR) and path.is_file():
                await route.fulfill(body=golden_html(path), content_type="text/html; charset=utf-8")
                return
            await route.abort()
            return
        if url.startswith(FIXTURES_URL) and fixtures is not None:
            path = (fixtures / url.removeprefix(FIXTURES_URL).split("?")[0].split("#")[0].lstrip("/")).resolve()
            if path.is_relative_to(fixtures.resolve()) and path.is_file():
                await route.fulfill(path=path)
                return
            await route.abort()
            return
        await route.fallback()

    return route


def page_specs(fixtures: Path | None, public: bool, only: list[str] | None) -> list[PageSpec]:
    specs = [
        PageSpec(
            "golden", str(path.relative_to(GOLDEN_DIR).with_suffix("")), f"{GOLDEN_URL}{path.relative_to(GOLDEN_DIR)}"
        )
        for path in sorted(GOLDEN_DIR.rglob("*.html"))
    ]
    if fixtures is not None:
        specs += [
            PageSpec("fixture", path.stem, f"{FIXTURES_URL}{path.name}") for path in sorted(fixtures.glob("*.html"))
        ]
    if public:
        specs += [PageSpec("public", name, url) for name, url in PUBLIC_PAGES.items()]
    if only:
        specs = [spec for spec in specs if any(token in spec.name for token in only)]
    return specs


async def open_page(session: notte.Session, spec: PageSpec, router: Callable[[Route], Awaitable[None]]) -> None:
    page = session.window.page
    await page.unroute_all()
    _ = await page.route("**/*", router)
    _ = await page.goto(spec.url, wait_until="load" if spec.group != "public" else "domcontentloaded", timeout=45_000)
    if spec.group == "public":
        try:
            await page.wait_for_load_state("networkidle", timeout=8_000)
        except Exception:
            pass
        await page.wait_for_timeout(1_000)


# ---------------------------------------------------------------------------------------------
# Chromium's accessibility tree, joined to the DOM nodes by XPath


async def ax_tree_names(cdp: CDPSession) -> dict[str, str | None]:
    """Names of the main frame's elements by their `buildDomNode.js` XPath (None: XPath not unique)."""
    ax: dict[str, Any] = await cdp.send("Accessibility.getFullAXTree")  # pyright: ignore[reportUnknownMemberType]
    document: dict[str, Any] = await cdp.send("DOM.getDocument", {"depth": -1, "pierce": True})  # pyright: ignore[reportUnknownMemberType]
    names: dict[int, str] = {}
    for node in cast(list[dict[str, Any]], ax["nodes"]):
        backend_id = node.get("backendDOMNodeId")
        if backend_id is not None and not node.get("ignored", False):
            names[backend_id] = str(node.get("name", {}).get("value", ""))
    by_xpath: dict[str, str | None] = {}

    def visit(children: list[dict[str, Any]], prefix: list[str]) -> None:
        elements = [child for child in children if child.get("nodeType") == 1]
        counts = Counter(child["localName"] for child in elements)
        seen: Counter[str] = Counter()
        for child in elements:
            tag = child["localName"]
            seen[tag] += 1
            segments = prefix + [tag if counts[tag] == 1 else f"{tag}[{seen[tag]}]"]
            xpath = "/".join(segments)
            if child["backendNodeId"] in names:
                by_xpath[xpath] = None if xpath in by_xpath else names[child["backendNodeId"]]
            for shadow in child.get("shadowRoots", []):
                visit(shadow.get("children", []), [])
            visit(child.get("children", []), segments)

    visit(cast(dict[str, Any], document["root"]).get("children", []), [])
    return by_xpath


def attach_ax_names(dom: DomNode, names: dict[str, str | None]) -> None:
    for node in dom.interaction_nodes():
        selectors = node.computed_attributes.selectors
        if selectors is None or selectors.in_iframe:
            continue
        name = names.get(selectors.xpath_selector)
        if name:
            object.__setattr__(node, "accessible_name", clean(name) or None)


def clean(name: str | None) -> str:
    return " ".join((name or "").split())[:MAX_NAME_LENGTH]


# ---------------------------------------------------------------------------------------------
# instrumentation: the DOM build step, the script payload, and the variant in use


@dataclass
class Probe:
    variant: str = "js"
    repeat: int = 1
    cdp: dict[int, CDPSession] = field(default_factory=dict)
    dom_ms: float = 0.0
    payload_bytes: int = 0
    last_dom: DomNode | None = None

    def install(self) -> None:
        original_parse = parsing.parse_dom
        original_load = parsing._load_payload  # pyright: ignore[reportPrivateUsage]
        scripts = {variant: variant_script(variant, self.repeat) for variant in VARIANTS}

        def load(payload: str | None) -> Any:
            self.payload_bytes += 0 if payload is None else len(payload.encode())
            return original_load(payload)

        async def parse(page: Page) -> DomNode:
            parsing.DOM_TREE_JS = scripts[self.variant]
            self.payload_bytes = 0
            start = time.perf_counter()
            dom = await original_parse(page)
            if self.variant == "cdp":
                cdp = self.cdp.get(id(page))
                if cdp is None:
                    cdp = self.cdp[id(page)] = await page.context.new_cdp_session(page)
                attach_ax_names(dom, await ax_tree_names(cdp))
            self.dom_ms = (time.perf_counter() - start) * 1000
            self.last_dom = dom
            return dom

        parsing._load_payload = load  # pyright: ignore[reportPrivateUsage]
        setattr(window_module, "parse_dom", parse)


def new_session() -> notte.Session:
    return notte.Session(headless=True, viewport_width=1280, viewport_height=720, chrome_args=CHROME_ARGS)


def pct(values: list[float], q: float) -> float:
    if len(values) == 1:
        return values[0]
    return statistics.quantiles(values, n=100, method="inclusive")[int(q) - 1]


# ---------------------------------------------------------------------------------------------
# accuracy


async def accuracy(specs: list[PageSpec], router: Callable[[Route], Awaitable[None]], out: Path | None) -> None:
    probe = Probe()
    probe.install()
    results: list[dict[str, Any]] = []
    async with new_session() as session:
        for spec in specs:
            try:
                await open_page(session, spec, router)
            except Exception as e:
                print(f"skip {spec.name}: {type(e).__name__} {e}")
                continue
            probe.variant = "js"
            _ = await session.aobserve()
            assert probe.last_dom is not None
            js = {n.id: clean(n.accessible_name) for n in probe.last_dom.interaction_nodes()}
            probe.variant = "computed"
            _ = await session.aobserve()
            assert probe.last_dom is not None
            nodes = {n.id: n for n in probe.last_dom.interaction_nodes()}
            chrome = {node_id: clean(n.accessible_name) for node_id, n in nodes.items()}
            # computedName vs the accessibility tree, where the XPath join is unique
            cdp = await session.window.page.context.new_cdp_session(session.window.page)
            ax = await ax_tree_names(cdp)
            await cdp.detach()
            ax_checked = ax_agree = 0
            for node_id, node in nodes.items():
                selectors = node.computed_attributes.selectors
                if selectors is None or selectors.in_iframe or selectors.xpath_selector not in ax:
                    continue
                ax_name = ax[selectors.xpath_selector]
                if ax_name is None:
                    continue
                ax_checked += 1
                ax_agree += clean(ax_name) == chrome[node_id]
            mismatches: list[dict[str, str]] = []
            common = [node_id for node_id in js if node_id in chrome]
            for node_id in common:
                if js[node_id] != chrome[node_id]:
                    node = nodes[node_id]
                    tag = node.attributes.tag_name if node.attributes is not None else "?"
                    mismatches.append({"id": str(node_id), "tag": tag, "js": js[node_id], "chrome": chrome[node_id]})
            result = {
                "group": spec.group,
                "page": spec.name,
                "elements": len(js),
                "named_js": sum(1 for name in js.values() if name),
                "named_chrome": sum(1 for name in chrome.values() if name),
                "compared": len(common),
                "equal": len(common) - len(mismatches),
                "ax_checked": ax_checked,
                "ax_agree": ax_agree,
                "mismatches": mismatches,
            }
            results.append(result)
            print(
                f"{spec.group:8} {spec.name:36} elements={result['elements']:4} named js={result['named_js']:4}"
                + f" chrome={result['named_chrome']:4} equal={result['equal']}/{result['compared']}"
                + f" ax-agree={ax_agree}/{ax_checked}"
            )
            for mismatch in mismatches[:12]:
                print(f"    {mismatch['id']:6} <{mismatch['tag']}> js={mismatch['js']!r} chrome={mismatch['chrome']!r}")
    if out is not None:
        _ = out.write_text(json.dumps(results, indent=2))


# ---------------------------------------------------------------------------------------------
# latency


async def latency(
    specs: list[PageSpec],
    router: Callable[[Route], Awaitable[None]],
    n: int,
    warmup: int,
    out: Path | None,
    same_page: bool,
    repeat: int,
) -> None:
    probe = Probe(repeat=repeat)
    probe.install()
    variants = SAME_PAGE_VARIANTS if same_page else VARIANTS
    shared = new_session() if same_page else None
    sessions = {variant: shared or new_session() for variant in variants}
    browsers = list({id(session): session for session in sessions.values()}.values())
    results: list[dict[str, Any]] = []
    for session in browsers:
        await session.astart()
    try:
        for spec in specs:
            try:
                for session in browsers:
                    await open_page(session, spec, router)
            except Exception as e:
                print(f"skip {spec.name}: {type(e).__name__} {e}")
                continue
            samples: dict[str, list[dict[str, float]]] = {variant: [] for variant in variants}
            for iteration in range(warmup + n):
                order = variants[iteration % len(variants) :] + variants[: iteration % len(variants)]
                for variant in order:
                    probe.variant = variant
                    start = time.perf_counter()
                    obs = await sessions[variant].aobserve()
                    total_ms = (time.perf_counter() - start) * 1000
                    if iteration < warmup:
                        continue
                    dom = probe.last_dom
                    assert dom is not None
                    interactions = dom.interaction_nodes()
                    space_json = obs.space.model_dump_json(
                        exclude=None if variant != "off" else {"interaction_actions": {"__all__": {"accessible_name"}}}
                    )
                    samples[variant].append(
                        {
                            "total_ms": total_ms,
                            "dom_ms": probe.dom_ms,
                            "payload_bytes": probe.payload_bytes,
                            "space_bytes": len(space_json.encode()),
                            "nodes": len(dom.flatten()),
                            "interactions": len(interactions),
                            "named": sum(1 for node in interactions if node.accessible_name),
                        }
                    )
            row: dict[str, Any] = {"group": spec.group, "page": spec.name}
            for variant, values in samples.items():
                totals = [value["total_ms"] for value in values]
                doms = [value["dom_ms"] for value in values]
                row[variant] = {
                    "total_p50": pct(totals, 50),
                    "total_p90": pct(totals, 90),
                    "dom_p50": pct(doms, 50),
                    "dom_p90": pct(doms, 90),
                    **{
                        key: statistics.median(value[key] for value in values)
                        for key in ("payload_bytes", "space_bytes", "nodes", "interactions", "named")
                    },
                }
            results.append(row)
            print(
                f"{spec.group:8} {spec.name:36} "
                + " | ".join(
                    f"{variant} dom {row[variant]['dom_p50']:.0f}/{row[variant]['dom_p90']:.0f}"
                    + f" total {row[variant]['total_p50']:.0f}/{row[variant]['total_p90']:.0f}"
                    for variant in variants
                )
                + f" | nodes={row['js']['nodes']:.0f} interactions={row['js']['interactions']:.0f}"
                + f" payload {row['off']['payload_bytes']:.0f}->{row['js']['payload_bytes']:.0f}"
                + f" space {row['off']['space_bytes']:.0f}->{row['js']['space_bytes']:.0f}",
                flush=True,
            )
            if out is not None:
                _ = out.write_text(json.dumps(results, indent=2))
    finally:
        for session in browsers:
            await session.astop()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    _ = parser.add_argument("command", choices=["accuracy", "latency"])
    _ = parser.add_argument("--fixtures", type=Path, help="a directory of *.html pages to add")
    _ = parser.add_argument("--public", action="store_true", help="add the public sites")
    _ = parser.add_argument("--only", nargs="*", help="only the pages whose name contains one of these")
    _ = parser.add_argument("-n", type=int, default=10, help="observes per page and variant (latency)")
    _ = parser.add_argument("--warmup", type=int, default=2, help="observes per variant not measured (latency)")
    _ = parser.add_argument("--same-page", action="store_true", help="off and js only, in one browser (latency)")
    _ = parser.add_argument("--repeat", type=int, default=1, help="name computations per element in js (latency)")
    _ = parser.add_argument("--out", type=Path, help="write the results as JSON")
    args = parser.parse_args()
    specs = page_specs(args.fixtures, args.public, args.only)
    router = make_router(args.fixtures)
    if args.command == "accuracy":
        asyncio.run(accuracy(specs, router, args.out))
    else:
        asyncio.run(latency(specs, router, args.n, args.warmup, args.out, args.same_page, args.repeat))


if __name__ == "__main__":
    main()
