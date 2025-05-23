import pytest
from dotenv import load_dotenv
from notte_agent.falco.agent import (
    FalcoAgent as Agent,
)
from notte_agent.falco.agent import (
    FalcoAgentConfig as AgentConfig,
)
from notte_integrations.pdf.docling import DoclingPDFReader

import notte


@pytest.mark.asyncio
async def test_scraping_2004_07606():
    config = AgentConfig().map_session(lambda session: session.agent_mode().not_headless())
    _ = load_dotenv()
    TASK = "go to https://arxiv.org/pdf/2004.07606 and get the II part of the paper word by word"
    EXPECTED_ANSWER = "II. RELATED WORK\n\nSeveral blockchain-based systems have been proposed for improving the traceability of products in supply chains. POMS [3] is a system for managing product ownership using the blockchain to prevent distribution of counterfeits in the post-supply chain. Kim et al. [4] proposed a method for tracking products from the materials stage by repeated consumption and production of traceable resource units (TRUs). Huang et al. [5] proposes a method that can be applied to the food supply chain, which features high-frequency distribution, through the use of off-chain technology. However, the protecting the privacy of distribution information has not been considered in any methods."
    async with notte.Session(config=config.session) as session:
        agent = Agent(config=config, window=session.window, pdf_reader=DoclingPDFReader())

        response = await agent.run(task=TASK)
        assert response.answer == EXPECTED_ANSWER
