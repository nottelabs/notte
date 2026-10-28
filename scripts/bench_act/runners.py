# pyright: basic
"""Run one task or one probe page on a local `NotteSession`, recording every model call (decisions, writer calls,
tokens, cost, timings). Imported by `worker.py`, in the environment of the code under test.

Runners:
- notte-local: `session.aact()` with Jev through OpenRouter (accessible labels)
- notte-local-llm: the same with the LLM decider
- notte-local-html: notte-local with `NOTTE_ACT_LABELS=html`
- probe-local-jev / probe-local-llm: `achoose()` / `acheck()` questions with known answers
- notte-local-scripted / probe-local-scripted: `ScriptedDecider`, no model and no key: times the browser side
  (session, navigation, observe, execute) and the CI setup; its outcomes mean nothing
"""

import json
import os
import time
from typing import Any
from urllib.parse import urlsplit

import notte_llm.act as A
from notte_browser.errors import PlaywrightError
from notte_browser.session import NotteSession
from notte_core.act import Answer, Answers, DecisionState, Question, WriteContext
from notte_core.act.loop import _stop  # pyright: ignore[reportPrivateUsage]

from .model import Probe, Task

VIEWPORT: dict[str, Any] = {"viewport_width": 1120, "viewport_height": 780}
WRITER = "inception/mercury-3"
LLM_MODEL = "google/gemini-3.1-flash-lite"
PROBE_JS = """(() => { let consent = null, cart = null; try { consent = localStorage.getItem('consent');
    cart = localStorage.getItem('cart-contents') } catch (e) {}
  const frames = [...document.querySelectorAll('iframe')].map(f => { try { const d = f.contentDocument;
    return {src: f.src, inputs: [...d.querySelectorAll('input,select')].slice(0, 20).map(e => ({id: e.id,
      name: e.name, value: e.value}))} } catch (e) { return {src: f.src, error: 'cross-origin'} } });
  return JSON.stringify({url: location.href, title: document.title, consent, cart, frames,
  text: (document.body ? document.body.innerText : '').slice(0, 6000),
  tables: [...document.querySelectorAll('table tr')].slice(0, 30).map(tr => [...tr.cells].map(c => c.innerText.trim())),
  todos: [...document.querySelectorAll('.todo-list li')].map(li => ({text: li.innerText.trim(), done: li.classList.contains('completed')})),
  inputs: [...document.querySelectorAll('input,textarea,select')].slice(0, 40).map(e => ({tag: e.tagName.toLowerCase(),
    type: e.type, name: e.name, id: e.id, value: e.value, checked: !!e.checked, disabled: e.disabled}))}) })()"""
# the page right after the first navigation: where it landed, its HTTP status, its text (see `rules.site_miss`)
LANDING_JS = """(() => { const nav = performance.getEntriesByType('navigation')[0];
  return JSON.stringify({url: location.href, status: nav && nav.responseStatus ? nav.responseStatus : null,
  text: (document.body ? document.body.innerText : '').slice(0, 2000)}) })()"""


async def _landing(page: Any) -> dict[str, Any]:
    """`LANDING_JS` on the first page. A site that redirects on load (booking.com) destroys the page being read:
    read the page it lands on once it has loaded. The landing page is evidence for `rules.site_miss`, so failing to
    read it is recorded, not an error of the run."""
    try:
        return json.loads(await page.evaluate(LANDING_JS))
    except Exception:
        try:
            await page.wait_for_load_state("load", timeout=10000)
            return json.loads(await page.evaluate(LANDING_JS))
        except Exception as e:
            return {"url": page.url, "status": None, "text": "", "error": f"{type(e).__name__}: {e}"[:500]}


class Recorder:
    """Model calls of the current step, in order."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        # which decider method the LLM calls belong to
        self.phase: str = "write"

    def take(self) -> list[dict[str, Any]]:
        calls, self.calls = self.calls, []
        return calls


REC = Recorder()


def ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 1)


def _usage(usage: dict[str, Any] | None) -> dict[str, Any]:
    usage = usage or {}
    return {
        "input_tokens": usage.get("input_tokens", usage.get("prompt_tokens")),
        "output_tokens": usage.get("output_tokens", usage.get("completion_tokens")),
        "reasoning_tokens": (usage.get("completion_tokens_details") or {}).get("reasoning_tokens"),
        "cost": usage.get("cost"),
    }


def _top(probabilities: dict[str, float], n: int = 3) -> dict[str, float]:
    return dict(sorted(probabilities.items(), key=lambda kv: -kv[1])[:n])


class ScriptedDecider:
    """No model: scrolls down `SCROLLS` times (when the page scrolls), then answers DONE; every other question gets
    its first option."""

    SCROLLS = 2

    def __init__(self) -> None:
        self.operations = 0

    async def choose(self, state: DecisionState, questions: dict[str, Question]) -> Answers:
        answers = {}
        for key, question in questions.items():
            options = list(question.criteria)
            choice = options[0]
            if key == "operation":
                self.operations += 1
                scroll = self.operations <= self.SCROLLS and "SCROLL_DOWN" in options
                choice = "SCROLL_DOWN" if scroll else "DONE"
            # act checks a probability for every offered option
            probabilities = {option: float(option == choice) for option in options}
            answers[key] = Answer(choice=choice, probabilities=probabilities, confidence=1.0)
        return Answers(answers=answers, model="scripted")

    async def write(self, context: WriteContext) -> str | None:
        return None


def notte_decider(kind: str) -> Any:
    """The decider of `default_decider()` for `kind` (jev / llm), or `ScriptedDecider` (scripted), recording every
    model call."""
    if not getattr(A, "_bench_patched", False):
        complete = A._complete

        async def recorded(model: str, messages: Any, response_format: Any, max_tokens: int) -> Any:
            start = time.perf_counter()
            try:
                content, usage = await complete(model, messages, response_format, max_tokens)
            except Exception as e:
                REC.calls.append(
                    {
                        "kind": "llm",
                        "phase": REC.phase,
                        "model": model,
                        "ms": ms(start),
                        "error": f"{type(e).__name__}: {e}",
                    }
                )
                raise
            REC.calls.append(
                {"kind": "llm", "phase": REC.phase, "model": model, "ms": ms(start), "usage": _usage(usage)}
            )
            return content, usage

        A._complete = recorded
        setattr(A, "_bench_patched", True)

    writer = A.LlmWriter(WRITER, fallback_model=LLM_MODEL)
    if kind == "scripted":
        inner: Any = ScriptedDecider()
    elif kind == "jev":
        inner = A.JevDecider(route="openrouter", writer=writer)
    else:
        inner = A.LlmDecider(LLM_MODEL, writer=writer)

    class RecordingDecider:
        async def choose(self, state: DecisionState, questions: dict[str, Question]) -> Answers:
            start = time.perf_counter()
            REC.phase = "decide"
            try:
                answers = await inner.choose(state, questions)
            finally:
                REC.phase = "write"
            REC.calls.append(
                {
                    "kind": "decide",
                    "ms": ms(start),
                    "model": answers.model,
                    "usage": _usage(answers.usage),
                    "page_text_chars": len(state.page.text),
                    "elements": len(state.elements),
                    "request_chars": len(
                        json.dumps(
                            {
                                "state": state.model_dump(),
                                "questions": {k: q.model_dump() for k, q in questions.items()},
                            }
                        )
                    ),
                    "state": state.model_dump(),
                    "answers": {k: v.model_dump() for k, v in answers.answers.items()},
                }
            )
            return answers

        async def write(self, context: WriteContext) -> str | None:
            start = time.perf_counter()
            text = await inner.write(context)
            REC.calls.append({"kind": "write", "ms": ms(start), "text": text, "field": context.field})
            return text

        def close(self) -> None:
            if hasattr(inner, "close"):
                inner.close()

    return RecordingDecider()


def _decide_calls(calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Cost and tokens of each decision call: Jev answers carry their usage; LLM decisions are the LLM calls."""
    llm = [c for c in calls if c["kind"] == "llm" and c.get("phase") == "decide"]
    if llm:
        return [
            {
                "ms": c["ms"],
                "model": c["model"],
                **(c.get("usage") or {}),
                **({"error": c["error"]} if "error" in c else {}),
            }
            for c in llm
        ]
    return [{"ms": c["ms"], "model": c.get("model"), **c["usage"]} for c in calls if c["kind"] == "decide"]


def _writer_calls(calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "model": c["model"],
            "ms": c["ms"],
            **(c.get("usage") or {}),
            **({"error": c["error"]} if "error" in c else {}),
        }
        for c in calls
        if c["kind"] == "llm" and c.get("phase") != "decide"
    ]


def _step(i: int, result: Any, calls: list[dict[str, Any]], total_ms: float) -> dict[str, Any]:
    decides = [c for c in calls if c["kind"] == "decide"]
    writes = [c for c in calls if c["kind"] == "write"]
    last = decides[-1] if decides else {}
    target_answer = None
    if result.operation and last.get("answers"):
        target_answer = last["answers"].get(result.operation.lower() + "_target")
    elements = {e["index"]: e for e in (last.get("state") or {}).get("elements", [])}
    target_label = None
    if result.target:
        element = elements.get(result.target.split(":")[0]) or {}
        target_label = element.get("label")
        if ":" in result.target:
            option = next((o for o in element.get("options", []) if o["index"] == result.target), None)
            target_label = f"{target_label} → {option['label']}" if option else target_label
    op_answer = (last.get("answers") or {}).get("operation") or {}
    execution = result.execution
    return {
        "i": i,
        "status": result.status,
        "operation": result.operation,
        "target": result.target,
        "target_label": target_label,
        "text": result.value,
        "message": result.message,
        "execution_success": None if execution is None else execution.success,
        "op_confidence": op_answer.get("confidence"),
        "target_confidence": None if target_answer is None else target_answer.get("confidence"),
        "confidence": result.confidence,
        "op_probabilities": _top(result.operation_probabilities),
        "target_probabilities": _top(result.probabilities) if result.target else {},
        "decisions": len(decides),
        "stale_retry": len(decides) > 1,
        "url": (last.get("state") or {}).get("page", {}).get("url"),
        "page_text_chars": last.get("page_text_chars"),
        "elements": last.get("elements"),
        "request_chars": last.get("request_chars"),
        "decide": _decide_calls(calls),
        "writer": _writer_calls(calls),
        "write_texts": [w["text"] for w in writes],
        "write_fields": [w["field"] for w in writes],
        "timings": {
            "observe_ms": result.timings.observe_ms,
            "decide_ms": result.timings.decide_ms,
            "write_ms": result.timings.write_ms,
            "fresh_ms": result.timings.fresh_ms,
            "execute_ms": result.timings.execute_ms,
            "act_total_ms": result.timings.total_ms,
            "step_ms": total_ms,
        },
        "requests": [{"state": d["state"], "answers": d["answers"]} for d in decides],
    }


def _error_step(i: int, error: BaseException, calls: list[dict[str, Any]], total_ms: float) -> dict[str, Any]:
    return {
        "i": i,
        "status": "error",
        "error": f"{type(error).__name__}: {error}"[:1000],
        "decide": _decide_calls(calls),
        "writer": _writer_calls(calls),
        "timings": {"step_ms": total_ms},
        "requests": [{"state": c["state"], "answers": c["answers"]} for c in calls if c["kind"] == "decide"],
    }


def labels(runner: str) -> str:
    return "html" if runner.endswith("-html") else "accessible"


async def run_task(task: Task, url: str, decider_kind: str, label_mode: str) -> dict[str, Any]:
    os.environ["NOTTE_ACT_LABELS"] = label_mode
    decider = notte_decider(decider_kind)
    run: dict[str, Any] = {"steps": []}
    start = time.perf_counter()
    try:
        async with NotteSession(headless=True, **VIEWPORT) as session:
            run["session_start_ms"] = ms(start)
            start = time.perf_counter()
            try:
                _ = await session.aexecute(type="goto", url=url)
            except Exception as e:
                run["nav_error"] = f"{type(e).__name__}: {e}"[:1000]
                run["error"] = run["nav_error"]
                return run
            run["nav_ms"] = ms(start)
            page = session.window.page
            run["landing"] = await _landing(page)
            if task.pre_js:
                run["pre"] = json.loads(await page.evaluate(task.pre_js))
            results: list[Any] = []
            loop_start = time.perf_counter()
            for i in range(task.max_steps):
                _ = REC.take()
                step_start = time.perf_counter()
                try:
                    result = await session.aact(task.goal, raise_on_failure=False, decider=decider)
                except Exception as e:
                    run["steps"].append(_error_step(i, e, REC.take(), ms(step_start)))
                    run["error"] = run["steps"][-1]["error"]
                    break
                run["steps"].append(_step(i, result, REC.take(), ms(step_start)))
                results.append(result)
                if _stop(results):
                    break
            run["wall_ms"] = ms(loop_start)
            final_page = session.window.page
            try:
                payload = await final_page.evaluate(PROBE_JS)
            except PlaywrightError as error:
                if "Execution context was destroyed" not in str(error):
                    raise
                # A read interrupted by navigation is safe to repeat once after the existing load wait.
                await final_page.wait_for_load_state("load", timeout=10000)
                payload = await final_page.evaluate(PROBE_JS)
            final = json.loads(payload)
            if task.final_js:
                final["extra"] = json.loads(await final_page.evaluate(task.final_js))
            run["final"] = final
            run["tabs"] = [p.url for p in session.window.page.context.pages]
    except Exception as e:
        run["error"] = f"{type(e).__name__}: {e}"[:1000]
    finally:
        decider.close()
    return run


def _probe_record(probe: Probe, value: Any, error: BaseException | None, elapsed_ms: float) -> dict[str, Any]:
    record: dict[str, Any] = {
        "probe": probe.name,
        "kind": "choose" if probe.options else "check",
        "answer": probe.answer,
    }
    if error is not None:
        record["error"] = f"{type(error).__name__}: {error}"[:1000]
    record["ms"] = elapsed_ms
    calls = REC.take()
    record["decide"] = _decide_calls(calls)
    decides = [c for c in calls if c["kind"] == "decide"]
    if decides:
        record["page_text_chars"] = decides[-1]["page_text_chars"]
        record["elements"] = decides[-1]["elements"]
        record["request"] = {"state": decides[-1]["state"], "answers": decides[-1]["answers"]}
    if value is None:
        record["correct"] = False
    elif probe.options:
        record.update(choice=value.choice, probabilities=value.probabilities, confidence=value.confidence)
        record["p_answer"] = value.probabilities.get(probe.answer)
        record["correct"] = value.choice == probe.answer
    else:
        record["p_yes"] = value
        record["p_answer"] = value if probe.answer == "YES" else 1 - value
        record["correct"] = (value >= 0.5) == (probe.answer == "YES")
    return record


async def run_probes(probes: list[Probe], url: str, decider_kind: str) -> dict[str, Any]:
    decider = notte_decider(decider_kind)
    run: dict[str, Any] = {"probes": []}
    try:
        async with NotteSession(headless=True, **VIEWPORT) as session:
            try:
                _ = await session.aexecute(type="goto", url=url)
            except Exception as e:
                run["nav_error"] = f"{type(e).__name__}: {e}"[:1000]
                run["error"] = run["nav_error"]
                return run
            page = session.window.page
            run["landing"] = await _landing(page)
            if urlsplit(page.url).hostname == "consent.google.com":
                # setup, not measured: the probes ask about the page behind Google's consent wall
                await page.get_by_role("button", name="Reject all").first.click()
                await page.wait_for_url("**/travel/flights/**", timeout=15000)
                await page.wait_for_timeout(2000)
                run["consent_rejected"] = True
            run["probe_url"] = page.url
            for probe in probes:
                _ = REC.take()
                start = time.perf_counter()
                value: Any = None
                error: BaseException | None = None
                try:
                    if probe.options:
                        value = await session.achoose(probe.question, probe.options, decider=decider)
                    else:
                        value = await session.acheck(probe.question, decider=decider)
                except Exception as e:
                    error = e
                run["probes"].append(_probe_record(probe, value, error, ms(start)))
            run["probe_url_end"] = page.url
    except Exception as e:
        run["error"] = f"{type(e).__name__}: {e}"[:1000]
    finally:
        decider.close()
    return run
