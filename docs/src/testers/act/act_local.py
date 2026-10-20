# @sniptest filename=act_local.py
# @sniptest typecheck_only=true
import notte

# needs OPENROUTER_API_KEY (Jev through OpenRouter, and the text writer), and `pip install "notte[llm]"`
with notte.Session() as session:
    _ = session.execute(type="goto", url="https://en.wikipedia.org/wiki/Main_Page")

    # one observe -> decide -> execute step per call
    result = session.act("type Ada Lovelace in the search box")
    print(result.status, result.action, result.confidence)
    print(result.timings)  # observe / decide / write / fresh / execute, in ms

    result = session.act("open the Ada Lovelace article")
    assert result.success
