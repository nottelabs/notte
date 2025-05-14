import time

from loguru import logger
from notte_core.actions.space import ActionSpace, SpaceCategory
from notte_core.browser.snapshot import BrowserSnapshot
from notte_core.llms.engine import StructuredContent
from notte_core.llms.service import LLMService


class PageCategoryPipe:
    def __init__(self, llmserve: LLMService, verbose: bool = False) -> None:
        self.llmserve: LLMService = llmserve
        self.verbose: bool = verbose

    def forward(self, snapshot: BrowserSnapshot, space: ActionSpace) -> SpaceCategory:
        description = f"""
- URL: {snapshot.metadata.url}
- Title: {snapshot.metadata.title}
- Description: {space.description or "No description available"}
""".strip()

        start_time = time.time()
        response = self.llmserve.completion(
            prompt_id="document-category/optim",
            variables={"document": description},
        )
        end_time = time.time()

        sc = StructuredContent(outer_tag="document-category")
        category = sc.extract(response.choices[0].message.content)  # type: ignore

        if self.verbose:
            logger.info(f"🏷️ Page categorisation: {category} (took {end_time - start_time:.2f} seconds)")
        return SpaceCategory(category)
