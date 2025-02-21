from typing import Required, TypedDict, Unpack

from notte.browser.processed_snapshot import ProcessedBrowserSnapshot
from notte.data.space import DataSpace
from notte.errors.llm import LLMnoOutputCompletionError
from notte.llms.engine import StructuredContent
from notte.llms.service import LLMService
from notte.pipe.rendering.pipe import DomNodeRenderingConfig, DomNodeRenderingPipe


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
        context: ProcessedBrowserSnapshot,
        max_tokens: int,
    ) -> str:
        # TODO: add DIVID & CONQUER once this is implemented
        document = DomNodeRenderingPipe.forward(node=context.node, config=self.config)
        document = self.llmserve.clip_tokens(document, max_tokens)
        return document

    def forward(
        self,
        context: ProcessedBrowserSnapshot,
        **params: Unpack[LlmDataScrapingDict],
    ) -> DataSpace:

        document = self._render_node(context, params["max_tokens"])
        # make LLM call
        prompt = "only_main_content" if params["only_main_content"] else "all_data"
        response = self.llmserve.completion(prompt_id=f"data-extraction/{prompt}", variables={"document": document})
        if response.choices[0].message.content is None:  # type: ignore
            raise LLMnoOutputCompletionError()
        response_text = str(response.choices[0].message.content)  # type: ignore
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
