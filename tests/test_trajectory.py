from collections import defaultdict

import pytest
from notte_agent.falco.agent import FalcoAgent
from notte_core.actions import ClickAction, FillAction
from notte_core.agent_types import AgentCompletion
from notte_core.browser.observation import ExecutionResult, Observation, Screenshot
from notte_core.trajectory import StepBundle, TrajectoryHoldee

import notte


def test_trajectory_and_view():
    with notte.Session(headless=True) as session:
        # first agent

        original_view = session.trajectory.view()

        # step 1
        _ = original_view.start_step()
        original_view.append(Observation.empty(), force=True)
        original_view.append(AgentCompletion.initial(url="https://google.com"), force=True)
        _ = original_view.stop_step()

        # second view
        second_view = session.trajectory.view()

        # step 2
        _ = original_view.start_step()
        original_view.append(ExecutionResult(action=ClickAction(id="B1"), success=True, message="clicked"), force=True)
        original_view.append(Observation.empty(), force=True)
        _ = original_view.stop_step()

        # step 3
        _ = original_view.start_step()
        original_view.append(Observation.empty(), force=True)
        _ = original_view.stop_step()

        original_view.stop()

        # only 2 steps
        late_view = session.trajectory._view(stop=len(original_view._elements) - 1)  # pyright: ignore [reportPrivateUsage]

        # agent steps
        assert session.trajectory.num_steps == 3
        assert original_view.num_steps == 3
        assert second_view.num_steps == 2
        assert late_view.num_steps == 2

        # elements in traj
        assert len(session.trajectory) == 5
        assert len(original_view) == 5
        assert len(second_view) == 3
        assert len(late_view) == 4

        # number of observations
        assert len(list(session.trajectory.observations())) == 3
        assert len(list(original_view.observations())) == 3
        assert len(list(second_view.observations())) == 2
        assert len(list(late_view.observations())) == 2

        # number of action exec
        assert len(list(session.trajectory.execution_results())) == 1
        assert len(list(original_view.execution_results())) == 1
        assert len(list(second_view.execution_results())) == 1
        assert len(list(late_view.execution_results())) == 1

        # number of completions
        assert len(list(session.trajectory.agent_completions())) == 1
        assert len(list(original_view.agent_completions())) == 1
        assert len(list(second_view.agent_completions())) == 0
        assert len(list(late_view.agent_completions())) == 1


def test_trajectory_callbacks():
    with notte.Session(headless=True) as session:
        # first agent

        view = session.trajectory.view()

        callback_calls: dict[str, int] = defaultdict(lambda: 0)

        init_comp = AgentCompletion.initial(url="https://google.com")
        init_exec = ExecutionResult(action=ClickAction(id="B1"), success=True, message="clicked")
        init_obs = Observation.empty()

        def observe_call(obs: Observation):
            callback_calls["obs"] += 1
            assert obs is init_obs

        def exec_call(res: ExecutionResult):
            callback_calls["exec"] += 1
            assert res is init_exec

        def comp_call(comp: AgentCompletion):
            callback_calls["comp"] += 1
            assert comp is init_comp

        def any_call(elem: TrajectoryHoldee):
            callback_calls["any"] += 1
            assert (elem is init_obs) or (elem is init_exec) or (elem is init_comp)

        def step_call_1(step: StepBundle):
            callback_calls["step"] += 1
            assert step.observation is init_obs
            assert step.agent_completion is None
            assert step.execution_result is None

        def step_call_2(step: StepBundle):
            callback_calls["step"] += 1
            assert step.observation is init_obs
            assert step.agent_completion is init_comp
            assert step.execution_result is init_exec

        view.set_callback("observation", observe_call)
        view.set_callback("execution_result", exec_call)
        view.set_callback("agent_completion", comp_call)
        view.set_callback("any", any_call)
        view.set_callback("step", step_call_1)

        # step 1
        _ = view.start_step()
        view.append(init_obs, force=True)
        _ = view.stop_step()

        view.set_callback("step", step_call_2)

        # step 2
        _ = view.start_step()
        view.append(init_comp, force=True)
        view.append(init_exec, force=True)
        view.append(init_obs, force=True)
        _ = view.stop_step()

        assert callback_calls["obs"] == 2
        assert callback_calls["comp"] == 1
        assert callback_calls["exec"] == 1
        assert callback_calls["any"] == 4

        assert callback_calls["step"] == 2


def test_trajectory_callback_from_session():
    with notte.Session(headless=True) as session:
        # first agent

        view = session.trajectory.view()

        callback_calls: dict[str, int] = defaultdict(lambda: 0)

        def observe_call(obs: Observation):
            callback_calls["obs"] += 1

        def exec_call(res: ExecutionResult):
            callback_calls["exec"] += 1

        def comp_call(comp: AgentCompletion):
            callback_calls["comp"] += 1

        def screenshot_call(screen: Screenshot):
            callback_calls["screen"] += 1

        def any_call(elem: TrajectoryHoldee):
            callback_calls["any"] += 1

        view.set_callback("observation", observe_call)
        view.set_callback("execution_result", exec_call)
        view.set_callback("agent_completion", comp_call)
        view.set_callback("screenshot", screenshot_call)
        view.set_callback("any", any_call)

        _ = session.observe()
        _ = session.execute(type="goto", value="https://google.com")
        _ = session.observe()
        _ = session.execute(type="reload", value="https://github.com")
        _ = session.observe()
        _ = session.execute(type="fill", value="searching on google", id="I1")

        assert callback_calls["obs"] == 3
        assert callback_calls["exec"] == 3
        assert callback_calls["screen"] == 3
        assert callback_calls["any"] == 9


@pytest.mark.asyncio
async def test_agent_observes_page_correctly():
    with notte.Session(headless=True) as session:
        _ = session.execute(type="goto", value="https://duckduckgo.com")
        agent = notte.Agent(session=session, max_steps=1).create_agent()
        assert isinstance(agent, FalcoAgent)
        task = "fill in the search bar with 'einstein'"
        resp = await agent.arun(task=task)

        # since the agent observed, it saw the page and saw it can already fill
        action = resp.steps[-1].action
        assert isinstance(action, FillAction)
        assert action.id == "I1"
        assert not resp.success
