# @sniptest filename=ab_testing.py
import asyncio

from notte_sdk.endpoints.agents import BatchRemoteAgent


async def main():
    # Test different models
    models = ["gemini/gemini-2.0-flash", "anthropic/claude-3.5-sonnet", "openai/gpt-4o"]

    results = []
    for model in models:
        batch_agent = BatchRemoteAgent(session=session, reasoning_model=model, _client=client)

        result = await batch_agent.run(task="Complex task", n_jobs=3, strategy="first_success")

        results.append({"model": model, "success": result.success, "steps": len(result.steps)})

    # Compare which model performed best


asyncio.run(main())
