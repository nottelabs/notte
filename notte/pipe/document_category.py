from notte.actions.space import PossibleActionSpace, SpaceCategory
from notte.browser.context import Context
from notte.llms.engine import StructuredContent
from notte.llms.service import LLMService


class DocumentCategoryPipe:

    def __init__(self, llmserve: LLMService | None = None) -> None:
        self.llmserve: LLMService = llmserve or LLMService()

    def forward(self, context: Context, space: PossibleActionSpace) -> PossibleActionSpace:
        description = f"""
- URL: {context.snapshot.url}
- Title: {context.snapshot.title}
- Description: {space.description or "No description available"}
""".strip()

        response = self.llmserve.completion(
            prompt_id="document-category/optim",
            variables={"document": description},
        )

        sc = StructuredContent(outer_tag="document-caterogy")
        category = sc.extract(response.choices[0].message.content)  # type: ignore
        space.category = SpaceCategory(category)
        return space
