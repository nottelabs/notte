# Notte Browser

Local, Playwright-based browser sessions (`notte.Session`) with the same `execute` / `observe` / `scrape` API as Notte cloud sessions.

## Features

- **Browser management**: local Chromium (patchright) or any browser reachable over CDP (`cdp_url`)
- **Observations**: turns pages into a list of interaction actions plus clean markdown
- **Actions**: click, fill, select, upload, scroll, tabs, ... by action id or selector
- **Scraping**: markdown, images, and structured data with the optional `llm` extra
- **Vaults and personas**: fill credentials from a vault without exposing them

## Installation

```bash
pip install notte-browser
patchright install --with-deps chromium
# structured scraping (`scrape(instructions=..., response_format=...)`) uses an LLM:
pip install 'notte-browser[llm]'
```

The LLM extra reads `NOTTE_LLM_MODEL` (default `gemini/gemini-3.5-flash`, or `vertex_ai/gemini-3.5-flash` when
`GOOGLE_APPLICATION_CREDENTIALS` is set) and the matching provider API key from the environment.

## Usage

```python
from notte_browser.session import NotteSession

with NotteSession(headless=True) as session:
    _ = session.execute(type="goto", url="https://www.notte.cc")
    obs = session.observe()
    markdown = session.scrape()
```
