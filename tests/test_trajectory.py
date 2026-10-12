from collections import defaultdict

import pytest
from notte_core.actions import ClickAction
from notte_core.browser.observation import ExecutionResult, Observation, Screenshot, TimedSpan
from notte_core.trajectory import TrajectoryHoldee

import notte


def _click_result() -> ExecutionResult:
    span = TimedSpan.empty()
    return ExecutionResult(
        action=ClickAction(id="B1"),
        success=True,
        message="clicked",
        started_at=span.started_at,
        ended_at=span.ended_at,
    )


@pytest.mark.asyncio
async def test_trajectory_and_view():
    with notte.Session(headless=True) as session:
        original_view = session.trajectory.view()
        await original_view.append(Observation.empty(), force=True)

        # second view only sees what is appended after its creation
        second_view = session.trajectory.view()
        await original_view.append(_click_result(), force=True)
        await original_view.append(Observation.empty(), force=True)
        await original_view.append(Observation.empty(), force=True)
        await original_view.append(Observation.empty(), force=True)

        original_view.stop()

        # view without the last observation
        late_view = session.trajectory._view(stop=len(original_view.elements) - 1)  # pyright: ignore [reportPrivateUsage]

        session.trajectory.debug_log()
        assert len(session.trajectory) == 5
        assert len(original_view) == 5
        assert len(second_view) == 4
        assert len(late_view) == 4

        assert len(list(session.trajectory.observations())) == 4
        assert len(list(original_view.observations())) == 4
        assert len(list(second_view.observations())) == 3
        assert len(list(late_view.observations())) == 3

        assert len(list(session.trajectory.execution_results())) == 1
        assert len(list(original_view.execution_results())) == 1
        assert len(list(second_view.execution_results())) == 1
        assert len(list(late_view.execution_results())) == 1

        # a stopped view does not grow anymore
        await session.trajectory.append(Observation.empty())
        assert len(session.trajectory) == 6
        assert len(original_view) == 5
        assert len(second_view) == 5

        with pytest.raises(ValueError, match="Cannot append to a trajectory view"):
            await second_view.append(Observation.empty())


@pytest.mark.asyncio
async def test_trajectory_callbacks():
    with notte.Session(headless=True) as session:
        view = session.trajectory.view()

        callback_calls: dict[str, int] = defaultdict(lambda: 0)
        init_exec = _click_result()
        init_obs = Observation.empty()

        async def observe_call(obs: Observation):
            callback_calls["obs"] += 1
            assert obs is init_obs

        async def exec_call(res: ExecutionResult):
            callback_calls["exec"] += 1
            assert res is init_exec

        async def any_call(_: TrajectoryHoldee):
            callback_calls["any"] += 1

        view.set_callback("observation", observe_call)
        view.set_callback("execution_result", exec_call)
        view.set_callback("any", any_call)

        await view.append(init_obs, force=True)
        await view.append(init_exec, force=True)
        await view.append(init_obs, force=True)

        assert callback_calls["obs"] == 2
        assert callback_calls["exec"] == 1
        assert callback_calls["any"] == 3


@pytest.mark.asyncio
async def test_trajectory_callback_from_session():
    with notte.Session(headless=True) as session:
        view = session.trajectory.view()

        callback_calls: dict[str, int] = defaultdict(lambda: 0)

        async def observe_call(obs: Observation):
            callback_calls["obs"] += 1

        async def exec_call(res: ExecutionResult):
            callback_calls["exec"] += 1

        async def screenshot_call(screen: Screenshot):
            callback_calls["screen"] += 1

        async def any_call(elem: TrajectoryHoldee):
            callback_calls["any"] += 1

        view.set_callback("observation", observe_call)
        view.set_callback("execution_result", exec_call)
        view.set_callback("screenshot", screenshot_call)
        view.set_callback("any", any_call)

        _ = session.observe()
        _ = session.execute(type="goto", url="https://www.google.com")
        _ = session.observe()
        _ = session.execute(type="reload")
        _ = session.observe()
        _ = session.execute(type="click", id="B1")

        assert callback_calls["obs"] == 3
        assert callback_calls["exec"] == 3
        assert callback_calls["screen"] == 3
        assert callback_calls["any"] == 9
