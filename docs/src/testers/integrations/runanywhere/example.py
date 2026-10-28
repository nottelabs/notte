# @sniptest filename=runanywhere.py
# @sniptest typecheck_only=true
from pydantic import BaseModel

import notte

# needs `pip install "notte[llm]"` and the NOTTE_LLM_* variables pointing at RunAnywhere


class Article(BaseModel):
    title: str
    born: str


with notte.Session() as session:
    _ = session.execute(type="goto", url="https://en.wikipedia.org/wiki/Main_Page")

    # act() decides each step and writes field values with the RunAnywhere model
    result = session.act("type Ada Lovelace in the search box")
    result = session.act("open the Ada Lovelace article")
    assert result.success

    # structured extraction uses the same endpoint
    article = session.scrape(instructions="Extract the article title and birth date", response_format=Article)
    print(article)
