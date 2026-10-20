# @sniptest filename=deciders.py
# @sniptest typecheck_only=true
from notte_llm import JevDecider, LlmDecider, LlmWriter

import notte

# explicit deciders instead of the environment-based default
# the writer asks `fallback_model` once when its own provider refuses on content-policy grounds
writer = LlmWriter("inception/mercury-2.5", fallback_model="google/gemini-3.1-flash-lite")
jev = JevDecider(writer=writer)  # TYPESAFE_API_KEY
llm = LlmDecider("google/gemini-3.1-flash-lite")  # OPENROUTER_API_KEY

with notte.Session() as session:
    _ = session.execute(type="goto", url="https://en.wikipedia.org/wiki/Main_Page")
    typed = session.act("type Ada Lovelace in the search box", decider=jev)
    submitted = session.act("submit the search", decider=llm)
    print(typed.status, submitted.status)
