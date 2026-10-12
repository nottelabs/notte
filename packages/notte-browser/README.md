# Notte Browser

Local, Playwright-based browser sessions (`notte.Session`) with the same `execute` / `observe` / `scrape` API as Notte cloud sessions.

## Features

- **Browser management**: local Chromium (patchright) or any browser reachable over CDP (`cdp_url`)
- **Observations**: turns pages into a list of interaction actions plus clean markdown
- **Actions**: click, fill, select, upload, scroll, tabs, ... by action id or selector
- **Scraping**: markdown and images; structured data through a pluggable extractor (`notte_core.data.extraction.StructuredExtractor`)
- **Vaults and personas**: fill credentials from a vault without exposing them

## Installation

```bash
pip install notte-browser
patchright install --with-deps chromium
# structured scraping (`scrape(instructions=..., response_format=...)`) needs an extractor, e.g. the LLM one:
pip install notte-llm
```

notte-browser never calls an LLM itself: structured scraping hands the page markdown to the session's extractor.
Pass one with `NotteSession(extractor=...)`; when none is passed and [notte-llm](../notte-llm/README.md) is installed,
its `LlmExtractor` is used.

## Usage

```python
from notte_browser.session import NotteSession

with NotteSession(headless=True) as session:
    _ = session.execute(type="goto", url="https://www.notte.cc")
    obs = session.observe()
    markdown = session.scrape()
```
