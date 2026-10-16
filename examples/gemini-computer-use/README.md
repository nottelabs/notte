# Gemini Computer Use with Notte

Use Gemini's browser computer-use tool with a Notte cloud browser. Requires Python 3.11+ or Node.js 24+, a Notte key, and a paid Gemini API project.

Browser actions, safety handling, and cleanup are verified with real Notte browsers and injected Gemini responses. End-to-end model tasks remain unverified: Gemini 3.8 returned HTTP 503, and 3.5 Flash Lite returned an explicit safety block on the test form. The loop preserves those provider decisions.

Create a Gemini key at [AI Studio](https://aistudio.google.com/api-keys). Enable [billing](https://aistudio.google.com/billing) for its project; computer use is unavailable on the free tier.

```bash
export NOTTE_API_KEY=your-notte-api-key
export GEMINI_API_KEY=your-gemini-api-key
```

## Python

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python agent.py "Go to https://example.com and read its page title."
```

## TypeScript

```bash
npm ci
npm start -- "Go to https://example.com and read its page title."
```

Both examples return the agent's answer, page title, session ID, and executed action count. No local Chromium installation is needed. Each run owns a three-minute Notte session and closes it on success or failure.

The default model is `gemini-3.8-flash`. Set `GEMINI_MODEL` to use another [supported Computer Use model](https://ai.google.dev/gemini-api/docs/computer-use#model-versions).

The browser loop supports Gemini's browser actions, uses screenshots rather than the DOM, and stops after twelve turns. It stops on blocked actions or requests for user confirmation. It never acknowledges those requests automatically. Add your application's approval flow before adapting this example to tasks that require confirmation.

## Verify

`npm test` and `python -m unittest -v test_agent.py` check that safety decisions prevent browser access. Set `NOTTE_GEMINI_LIVE=1`, `NOTTE_API_KEY`, and an explicit `NOTTE_API_URL` to also check form actions, confirmation handling, injected provider failures, and browser cleanup. These checks do not call Gemini.

Set `NOTTE_GEMINI_MODEL_LIVE=1` and a funded `GEMINI_API_KEY` to run the actual Gemini model against the cloud browser in each language. Pull requests verify browser actions with injected provider responses; model tests use the repository key only on main pushes or manual runs on main. A skipped model test does not establish model compatibility.
