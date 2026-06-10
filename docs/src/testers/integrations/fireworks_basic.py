# @sniptest filename=fireworks_basic.py
import notte

with notte.Session() as session:
    agent = notte.Agent(
        session=session,
        reasoning_model="fireworks_ai/accounts/fireworks/models/kimi-k2p5",
    )
    response = agent.run(task="Go to news.ycombinator.com and return the top three stories.")
