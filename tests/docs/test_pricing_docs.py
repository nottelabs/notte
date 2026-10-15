"""The pricing page quotes the current browser rate."""

import re
from pathlib import Path

DOCS = Path(__file__).resolve().parents[2] / "docs" / "src"
PRICING_CARDS = DOCS / "pricing.mdx"
BROWSER_RATE_PER_HOUR = 0.01


def _card_browser_rate() -> float:
    text = PRICING_CARDS.read_text()
    match = re.search(r'title="Browser Usage"[^*]*\*\*\$(\d+\.\d+) / hour\*\*', text, flags=re.DOTALL)
    assert match is not None, "browser usage card not found"
    return float(match.group(1))


def test_pricing_page_documents_the_browser_rate() -> None:
    assert _card_browser_rate() == BROWSER_RATE_PER_HOUR
