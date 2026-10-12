"""The two pricing pages quote the same browser rate and the worked example adds up."""

import re
from pathlib import Path

DOCS = Path(__file__).resolve().parents[2] / "docs" / "src"
PRICING_CARDS = DOCS / "pricing.mdx"
PRICING_INTRO = DOCS / "intro" / "pricing.mdx"
BROWSER_RATE_PER_HOUR = 0.01


def _search(pattern: str, text: str) -> re.Match[str]:
    match = re.search(pattern, text, flags=re.DOTALL)
    assert match is not None, f"pattern not found: {pattern}"
    return match


def _card_browser_rate() -> float:
    text = PRICING_CARDS.read_text()
    match = _search(r'title="Browser Usage"[^*]*\*\*\$(\d+\.\d+) / hour\*\*', text)
    return float(match.group(1))


def _table_browser_rate(text: str) -> float:
    match = _search(r"Browser Usage</td>\s*<td[^>]*>\\\$(\d+\.\d+) / hour</td>", text)
    return float(match.group(1))


def test_pricing_pages_document_the_browser_rate() -> None:
    assert _card_browser_rate() == BROWSER_RATE_PER_HOUR
    assert _table_browser_rate(PRICING_INTRO.read_text()) == BROWSER_RATE_PER_HOUR


def test_worked_example_adds_up() -> None:
    text = PRICING_INTRO.read_text()
    rate = _table_browser_rate(text)

    llm = float(_search(r"\*\*LLM Usage[^*]*\*\*:.*?≈ \*\*\\\$(\d+\.\d+)\*\*", text).group(1))
    browser = _search(r"\*\*Browser Usage\*\*: 1 minute at \\\$(\d+\.\d+)/hour ≈ \*\*\\\$(\d+\.\d+)\*\*", text)
    proxy = float(_search(r"\*\*Proxy Usage\*\*:.*?≈ \*\*\\\$(\d+\.\d+)\*\*", text).group(1))
    total = float(_search(r"\*\*Total: \\~\\\$(\d+\.\d+)\*\*", text).group(1))

    assert float(browser.group(1)) == rate, "the example quotes a different rate than the table"
    browser_cost = float(browser.group(2))
    assert browser_cost == round(rate / 60, 4), "one minute at the quoted rate"
    assert round(llm + browser_cost + proxy, 3) == total
