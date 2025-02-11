def pytest_addoption(parser):
    parser.addoption("--agent_llm", action="store", default="LLM model to use for the reasoning agent")
