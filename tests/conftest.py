def pytest_addoption(parser):
    parser.addoption("--agent_llm", action="store", default="LLM model to use for the reasoning agent")
    parser.addoption("--n_jobs", action="store", type=int, default=2, help="Number of parallel jobs to run")
