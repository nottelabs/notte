import asyncio
import re
from collections.abc import Callable

from notte.agents.falco.agent import FalcoAgent, FalcoAgentConfig
from notte.agents.falco.types import StepAgentOutput
from notte.browser.window import BrowserWindow
from notte.common.agent.base import BaseAgent
from notte.common.agent.types import AgentResponse
from notte.common.credential_vault.base import BaseVault
from notte.common.notifier.base import BaseNotifier, NotifierAgent
from notte.llms.engine import LlmModel
from notte.sdk.types import DEFAULT_MAX_NB_STEPS


class Agent:
    def __init__(
        self,
        headless: bool = False,
        reasoning_model: LlmModel = LlmModel.default(),  # type: ignore[reportCallInDefaultInitializer]
        max_steps: int = DEFAULT_MAX_NB_STEPS,
        use_vision: bool = True,
        # /!\ web security is disabled by default to increase agent performance
        # turn it off if you need to input confidential information on trajectories
        web_security: bool = False,
        vault: BaseVault | None = None,
        notifier: BaseNotifier | None = None,
    ):
        self.config: FalcoAgentConfig = (
            FalcoAgentConfig()
            .use_vision(use_vision)
            .model(reasoning_model, deep=True)
            .map_env(lambda env: (env.agent_mode().steps(max_steps).headless(headless).web_security(web_security)))
        )
        self.vault: BaseVault | None = vault
        self.notifier: BaseNotifier | None = notifier

    def create_agent(
        self,
        step_callback: Callable[[str, StepAgentOutput], None] | None = None,
        window: BrowserWindow | None = None,
    ) -> BaseAgent:
        agent = FalcoAgent(
            config=self.config,
            vault=self.vault,
            window=window,
            step_callback=step_callback,
        )
        if self.notifier:
            agent = NotifierAgent(agent, notifier=self.notifier)
        return agent

    async def async_run(self, task: str, url: str | None = None) -> AgentResponse:
        agent = self.create_agent()
        return await agent.run(task, url=url)

    def run(self, task: str, url: str | None = None) -> AgentResponse:
        agent = self.create_agent()
        return asyncio.run(agent.run(task, url=url))

    # Add to the relevant section that handles tasks
    async def handle_arxiv_task(self, task: str, url: str) -> str:
        """Handle ArXiv specific tasks."""
        if "arxiv.org" in url and "figures" in task.lower() and "tables" in task.lower():
            # Extract paper title from task
            paper_title_match = re.search(r'"([^"]+)"', task)
            if not paper_title_match:
                return "Could not identify paper title in task."
            
            paper_title = paper_title_match.group(1)
            
            # First navigate to ArXiv
            await self.act(GotoAction(url=url))
            
            # Search for the paper
            search_box = self.env.snapshot.dom_node.find("I1")  # Assuming I1 is the search box ID
            if search_box:
                await self.act(FillAction(id="I1", value=paper_title))
                await self.act(ClickAction(id="B1"))  # Assuming B1 is the search button ID
            
            # Find and click on the paper link
            await self.wait_for_page_load()
            paper_link = None
            for node in self.env.snapshot.dom_node.find_all():
                if paper_title.lower() in (node.text or "").lower():
                    paper_link = node
                    break
            
            if paper_link:
                await self.act(ClickAction(id=paper_link.id))
                await self.wait_for_page_load()
                
                # Now we're on the paper page, use PDF handler
                pdf_info = await self.env.browser_window.handle_pdf_content(self.env.browser_window.page.url)
                return f"{pdf_info['figures']} Figures, {pdf_info['tables']} Tables."
            
            return "Could not find the specified paper."
