import asyncio

from dotenv import load_dotenv
from notte_agent.falco.agent import (
    FalcoAgent as Agent,
)
from notte_agent.falco.agent import (
    FalcoAgentConfig as AgentConfig,
)
from notte_integrations.pdf.docling import DoclingPDFReader

import notte

_ = load_dotenv()

TASK = "go to arxiv and find Short Paper: Design and Evaluation of Privacy-preserved Supply Chain System based on Public Blockchain and extract the abstract of the pdf word by word"

if __name__ == "__main__":
    config = AgentConfig().map_session(lambda session: session.agent_mode().not_headless())

    async def run():
        async with notte.Session(config=config.session) as session:
            agent = Agent(config=config, window=session.window, pdf_reader=DoclingPDFReader())

            return await agent.run(task=TASK)

    print(asyncio.run(run()))
