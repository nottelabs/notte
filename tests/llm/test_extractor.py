from notte_browser.session import NotteSession
from notte_core.data.extraction import StructuredExtractor
from notte_llm import LlmExtractor


def test_llm_extractor_satisfies_protocol() -> None:
    assert isinstance(LlmExtractor(model="vertex_ai/gemini-3.5-flash"), StructuredExtractor)


def test_chosen_model_uses_a_cached_per_call_service() -> None:
    extractor = LlmExtractor(model="vertex_ai/gemini-3.5-flash")
    assert extractor._service(None) is extractor.llmserve  # pyright: ignore[reportPrivateUsage]
    assert extractor._service("vertex_ai/gemini-3.5-flash") is extractor.llmserve  # pyright: ignore[reportPrivateUsage]
    chosen = extractor._service("gemini/gemini-3.5-flash")  # pyright: ignore[reportPrivateUsage]
    assert chosen.base_model == "gemini/gemini-3.5-flash"
    assert extractor._service("gemini/gemini-3.5-flash") is chosen  # pyright: ignore[reportPrivateUsage]
    assert extractor.llmserve.base_model == "vertex_ai/gemini-3.5-flash"


def test_sessions_default_to_the_llm_extractor_when_installed() -> None:
    session = NotteSession()
    assert session._extractor is None  # pyright: ignore[reportPrivateUsage]
    assert isinstance(session._get_extractor(), LlmExtractor)  # pyright: ignore[reportPrivateUsage]
