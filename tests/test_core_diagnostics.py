from unittest.mock import MagicMock

import notte_core.logging as logging
import pytest
from notte_core import set_logger_mode
from notte_core.browser import dom_tree


def test_dom_diagnostics_bound_deduplicate_and_reset_samples(monkeypatch: pytest.MonkeyPatch) -> None:
    logger = MagicMock()
    monkeypatch.setattr(dom_tree, "logger", logger)
    dom_tree.flush_dom_errors()
    logger.reset_mock()
    for value in ["x" * 70, "x" * 70, "two", "three", "four", "five", "six"]:
        dom_tree.add_dom_errors({"extra"}, {"extra": value})
    dom_tree.flush_dom_errors()
    message = logger.debug.call_args.args[0]
    assert "x" * 50 in message and "x" * 51 not in message
    assert message.count("x" * 50) == 1
    assert "five" in message and "six" not in message
    dom_tree.flush_dom_errors()
    logger.debug.assert_called_once()
    dom_tree.add_dom_errors({"next"}, {"next": "fresh"})
    dom_tree.flush_dom_errors()
    assert "fresh" in logger.debug.call_args.args[0]
    assert "extra" not in logger.debug.call_args.args[0]


@pytest.mark.parametrize(("mode", "level"), [("developer", "DEBUG"), ("agent", "INFO"), ("user", "INFO")])
def test_logger_mode_uses_the_current_logger_provider(monkeypatch: pytest.MonkeyPatch, mode, level) -> None:
    backend_logger = MagicMock()
    monkeypatch.setattr(logging, "get_logger", lambda: backend_logger)
    set_logger_mode(mode)
    backend_logger.configure.assert_called_once()
    handler = backend_logger.configure.call_args.kwargs["handlers"][0]
    assert handler["level"] == level
    assert ("{function}" in handler["format"]) is (mode == "developer")
