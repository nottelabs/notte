from loguru import logger
from tiktoken import encoding_for_model
from typing_extensions import final

from notte.browser.context import Context
from notte.browser.driver import BrowserDriver
from notte.browser.node_type import NotteNode
from notte.browser.observation import DataSpace, ImageData
from notte.llms.engine import StructuredContent
from notte.llms.service import LLMService
from notte.pipe.preprocessing.a11y.tree import ProcessedA11yTree


@final
class DataScrapingPipe:

    def __init__(self, llmserve: LLMService | None = None, browser: BrowserDriver | None = None) -> None:
        self.llmserve: LLMService = llmserve or LLMService()
        self.browser: BrowserDriver | None = browser
        self.token_encoder = encoding_for_model("gpt-4o")
        self.max_tokens = 7300

    def forward(self, context: Context, scrape_images: bool = True) -> DataSpace:
        # TODO: add DIVID & CONQUER once this is implemented
        document = context.markdown_description(include_ids=False, include_images=scrape_images)
        if len(self.token_encoder.encode(document)) > self.max_tokens:
            logger.warning(
                (
                    "Document too long for data extraction: "
                    f" {len(self.token_encoder.encode(document))} tokens => use Simple AXT instead"
                )
            )
            tree = ProcessedA11yTree.from_a11y_tree(context.snapshot.a11y_tree)
            simple_node = NotteNode.from_a11y_node(tree.simple_tree, path=context.snapshot.url)
            document = Context.format(simple_node, include_ids=False)

        logger.warning(document)
        # make LLM call
        response = self.llmserve.completion(prompt_id="data-extraction/optim", variables={"document": document})
        sc = StructuredContent(outer_tag="data-extraction", inner_tag="markdown")
        if response.choices[0].message.content is None:  # type: ignore
            raise ValueError("No content in response")
        response_text = str(response.choices[0].message.content)  # type: ignore
        logger.debug(response_text)  # type: ignore
        text = sc.extract(
            response_text,
            fail_if_final_tag=False,
            fail_if_inner_tag=False,
        )
        return DataSpace(
            markdown=text,
            images=None,
            structured=None,
        )

    async def _scrape_images(self, context: Context) -> list[ImageData]:
        if self.browser is None:
            logger.error("Images cannot be scraped without a browser")
            return []
        image_nodes = context.node.image_nodes()
        out_images: list[ImageData] = []
        for node in image_nodes:
            if node.id is not None:
                out_images.append(
                    ImageData(
                        id=node.id,
                        # TODO: fill URL from browser session
                        url="TODO: FILL ME",
                    )
                )
        return out_images

    async def forward_async(self, context: Context) -> DataSpace:
        return self.forward(context)
