# Notte Browser Provider for Hermes Agent

This directory contains the files needed to add Notte as a cloud browser provider in [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent).

## What this does

Adds "Notte" as a browser provider option in the Hermes Agent onboarding wizard (`hermes setup`), alongside Browserbase, Browser Use, Firecrawl, and Camofox. When selected, Hermes Agent will use Notte's cloud browser infrastructure for all browser automation tasks.

## Files

### New files (to be added to hermes-agent)

| File | Destination in hermes-agent | Description |
|------|----------------------------|-------------|
| `tools/browser_providers/notte.py` | `tools/browser_providers/notte.py` | Provider implementation — creates/closes cloud browser sessions via Notte REST API |
| `tests/tools/test_notte_provider.py` | `tests/tools/test_notte_provider.py` | Unit tests (all HTTP calls mocked) |

### Existing files to modify (diffs shown below)

#### 1. `tools/browser_tool.py`

Add import (after line 82):
```python
from tools.browser_providers.notte import NotteProvider
```

Add to `_PROVIDER_REGISTRY` dict:
```python
_PROVIDER_REGISTRY: Dict[str, type] = {
    "browserbase": BrowserbaseProvider,
    "browser-use": BrowserUseProvider,
    "firecrawl": FirecrawlProvider,
    "notte": NotteProvider,  # <-- add this line
}
```

Add to the Environment Variables docstring:
```
- NOTTE_API_KEY: API key for Notte cloud mode (https://console.notte.cc)
```

#### 2. `hermes_cli/tools_config.py`

Add to the `"browser"` providers list (before the Camofox entry):
```python
{
    "name": "Notte",
    "tag": "Cloud browser with stealth, proxies & CAPTCHA solving",
    "env_vars": [
        {"key": "NOTTE_API_KEY", "prompt": "Notte API key", "url": "https://console.notte.cc"},
    ],
    "browser_provider": "notte",
    "post_setup": "agent_browser",
},
```

## How it works

The provider uses `requests` (already a hermes-agent dependency) to call the Notte REST API directly. **Zero new dependencies.**

### Session lifecycle

1. **Create**: `POST https://api.notte.cc/sessions/start` — returns `session_id`
2. **Get CDP URL**: `GET https://api.notte.cc/sessions/{id}/debug` — returns WebSocket CDP URL at `ws.cdp`
3. **Close**: `DELETE https://api.notte.cc/sessions/{id}/stop` — terminates the session

### Authentication

- `Authorization: Bearer {NOTTE_API_KEY}` header
- Users get their API key at https://console.notte.cc

### Environment variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `NOTTE_API_KEY` | Yes | — | API key from console.notte.cc |
| `NOTTE_API_URL` | No | `https://api.notte.cc` | Custom API base URL |
| `NOTTE_PROXIES` | No | `true` | Enable residential proxies |
| `NOTTE_SOLVE_CAPTCHAS` | No | `false` | Enable automatic CAPTCHA solving |
| `NOTTE_TIMEOUT_MINUTES` | No | `15` | Session timeout in minutes |

## PR strategy for hermes-agent

1. **Open a GitHub issue first** — titled "feat: Add Notte as a browser provider". Include benchmarks and value prop. This signals collaboration rather than a drive-by contribution.
2. **Fork hermes-agent**, create branch `feat/notte-browser-provider`
3. Apply the changes described above
4. Run tests: `pytest tests/tools/test_notte_provider.py -v`
5. Submit PR with title: `feat(tools): add Notte cloud browser provider`

### Suggested PR description

```
## Summary

- Add Notte (https://notte.cc) as a cloud browser provider alongside Browserbase, Browser Use, and Firecrawl
- Implement `NotteProvider` extending `CloudBrowserProvider` with full session lifecycle management
- Register Notte in the provider selection CLI wizard with `NOTTE_API_KEY` configuration

## Motivation

Notte is an open-source web agent framework (https://github.com/nottelabs/notte) providing
cloud browser infrastructure with built-in CAPTCHA solving, residential proxies, and stealth
capabilities. On the WebVoyager benchmark, Notte achieves 86.2% accuracy at 96.6% reliability,
2x faster than Browser Use (47s vs 113s per task). Adding Notte gives Hermes Agent users
another high-quality browser provider option.

## Implementation

Uses `requests` to call the Notte REST API directly — zero new dependencies. Session lifecycle:
POST /sessions/start → GET /sessions/{id}/debug (CDP URL) → DELETE /sessions/{id}/stop.

## Test plan

- [x] Unit tests with mocked HTTP responses for all provider methods
- [ ] Manual test: `hermes setup` shows Notte in provider list
- [ ] Manual test: configure Notte API key and run a browser task end-to-end
- [x] No new dependencies added
```
