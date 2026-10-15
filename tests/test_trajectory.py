from collections import defaultdict

import pytest
from notte_core.actions import ClickAction
from notte_core.observation import ExecutionResult, Observation, Screenshot, TimedSpan
from notte_core.trajectory import Trajectory, TrajectoryHoldee

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
async def test_trajectory_records_elements_in_order():
    trajectory = Trajectory()
    first_obs, result, screenshot, last_obs = (
        Observation.empty(),
        _click_result(),
        Screenshot(raw=b"png"),
        Observation.empty(),
    )
    for element in (first_obs, result, screenshot, last_obs):
        await trajectory.append(element)

    assert len(trajectory) == 4
    assert list(trajectory) == trajectory.elements == [first_obs, result, screenshot, last_obs]
    assert trajectory[1] is result
    assert list(trajectory.observations()) == [first_obs, last_obs]
    assert list(trajectory.execution_results()) == [result]
    assert list(trajectory.screenshots()) == [screenshot]
    assert trajectory.last_observation is last_obs
    assert trajectory.last_result is result
    assert trajectory.last_screenshot is screenshot
    assert repr(trajectory) == "Trajectory(observations=2, executions=1)"


def test_empty_trajectory_has_no_last_elements():
    trajectory = Trajectory()
    assert len(trajectory) == 0
    assert trajectory.last_observation is None
    assert trajectory.last_result is None
    assert trajectory.last_screenshot is None


@pytest.mark.asyncio
async def test_trajectory_callbacks():
    trajectory = Trajectory()
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

    trajectory.set_callback("observation", observe_call)
    trajectory.set_callback("execution_result", exec_call)
    trajectory.set_callback("any", any_call)

    await trajectory.append(init_obs)
    await trajectory.append(init_exec)
    await trajectory.append(init_obs)

    assert callback_calls["obs"] == 2
    assert callback_calls["exec"] == 1
    assert callback_calls["any"] == 3


@pytest.mark.live
@pytest.mark.asyncio
async def test_trajectory_callback_from_session():
    with notte.Session(headless=True) as session:
        callback_calls: dict[str, int] = defaultdict(lambda: 0)

        async def observe_call(obs: Observation):
            callback_calls["obs"] += 1

        async def exec_call(res: ExecutionResult):
            callback_calls["exec"] += 1

        async def screenshot_call(screen: Screenshot):
            callback_calls["screen"] += 1

        async def any_call(elem: TrajectoryHoldee):
            callback_calls["any"] += 1

        session.trajectory.set_callback("observation", observe_call)
        session.trajectory.set_callback("execution_result", exec_call)
        session.trajectory.set_callback("screenshot", screenshot_call)
        session.trajectory.set_callback("any", any_call)

        _ = session.observe()
        _ = session.execute(type="goto", url="https://www.google.com")
        _ = session.observe()
        _ = session.execute(type="reload")
        _ = session.observe()
        _ = session.execute(type="click", id="B1")
        # actions no longer append a screenshot; only explicit ones are recorded
        _ = session.screenshot()

        assert callback_calls["obs"] == 3
        assert callback_calls["exec"] == 3
        assert callback_calls["screen"] == 1
        assert callback_calls["any"] == 7
