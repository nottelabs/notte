import os

from openai import OpenAI
from openai.types.chat import ChatCompletion

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

with open("README.md", "r") as f:
    readme_content: str = f.read()

languages: list[str] = ["mandarin chinese", "spanish", "hindi", "russian", "bengali"]

for lang in languages:
    response: ChatCompletion = client.chat.completions.create(
        model="gpt-4",
        messages=[
            {
                "role": "system",
                "content": f"""You are a professional translator. Your task is to translate the following markdown text to {lang} with the following strict requirements:

1. Maintain EXACTLY the same markdown structure and formatting:
   - Keep all headers (#, ##, ###) at the same level
   - Preserve all code blocks (```) and their language specifications
   - Keep all links [text](url) in the same format
   - Maintain all lists (ordered and unordered) with the same indentation
   - Preserve all tables with the same structure
   - Keep all inline code (`code`) in the same format
   - Maintain all blockquotes (>)
   - Preserve all horizontal rules (---)

2. Translation rules:
   - Only translate the text content, not the markdown syntax
   - Keep all URLs unchanged
   - Keep all code examples unchanged
   - Keep all technical terms in English if they are commonly used in {lang}
   - Maintain the same line breaks and paragraph structure
   - Do not add or remove any sections
   - Do not modify the document structure in any way

3. Output:
   - Return only the translated markdown text
   - Do not include any explanations or notes
   - Ensure the output is valid markdown that renders exactly like the original""",
            },
            {"role": "user", "content": readme_content},
        ],
    )

    translated_content: str = response.choices[0].message.content

    with open(f"docs/readmes/{lang}.md", "w") as f:
        _ = f.write(translated_content)
