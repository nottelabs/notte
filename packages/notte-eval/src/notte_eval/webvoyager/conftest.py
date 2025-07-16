from _pytest.config.argparsing import Parser


def pytest_addoption(parser: Parser) -> None:
    parser.addoption("--use_sdk", action="store", default="false")
    parser.addoption("--model", action="store", default="vertex_ai/gemini-2.0-flash")
    parser.addoption("--n_runs", action="store", default="1")
    parser.addoption("--use_vision", action="store", default="true")
    parser.addoption("--headless", action="store", default="true")
    parser.addoption("--max_steps", action="store", default="20")
    parser.addoption("--proxies", action="store", default="false")
    parser.addoption("--user_agent", action="store", default="")
    parser.addoption("--task_dir", action="store", default="webvoyager/webvoyager_simple.jsonl")
