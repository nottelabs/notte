from typing import Required, Unpack

from notte_core.browser.snapshot import BrowserSnapshot
from notte_core.data.space import DataSpace
from notte_core.errors.llm import LLMnoOutputCompletionError
from notte_core.llms.engine import StructuredContent
from notte_core.llms.service import LLMService
from typing_extensions import TypedDict

from notte_browser.rendering.pipe import DomNodeRenderingConfig, DomNodeRenderingPipe


class LlmDataScrapingDict(TypedDict):
    only_main_content: Required[bool]
    max_tokens: Required[int]


class LlmDataScrapingPipe:
    """
    Data scraping pipe that scrapes data from the page
    """

    def __init__(self, llmserve: LLMService, config: DomNodeRenderingConfig) -> None:
        self.llmserve: LLMService = llmserve
        self.config: DomNodeRenderingConfig = config

    def _render_node(
        self,
        snapshot: BrowserSnapshot,
        max_tokens: int,
    ) -> str:
        # TODO: add DIVID & CONQUER once this is implemented
        document = DomNodeRenderingPipe.forward(node=snapshot.dom_node, config=self.config)
        document = self.llmserve.clip_tokens(document, max_tokens)
        return document

    def forward(
        self,
        snapshot: BrowserSnapshot,
        **params: Unpack[LlmDataScrapingDict],
    ) -> DataSpace:
        document = self._render_node(snapshot, params["max_tokens"])
        # make LLM call
        prompt = "only_main_content" if params["only_main_content"] else "all_data"
        response = self.llmserve.completion(prompt_id=f"data-extraction/{prompt}", variables={"document": document})
        if response.choices[0].message.content is None:  # type: ignore[arg-type]
            raise LLMnoOutputCompletionError()
        response_text = str(response.choices[0].message.content)  # type: ignore[arg-type]
        sc = StructuredContent(
            outer_tag="data-extraction",
            inner_tag="markdown",
            fail_if_final_tag=False,
            fail_if_inner_tag=False,
        )
        text = sc.extract(response_text)
        return DataSpace(
            markdown=text,
            images=None,
            structured=None,
        )
