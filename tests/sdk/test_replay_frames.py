import io

from notte_sdk import NotteClient
from PIL import Image

import notte


def test_sdk_screenshots():
    """Make sure everything is in bytes (and not base64 encoded), all in JPEG"""
    client = NotteClient()

    offset = slice(6, 10)

    ## local
    with notte.Session(headless=True) as session:
        _ = session.execute(dict(type="goto", url="https://linkedin.com"))
        obs = session.observe()

    for screenshot_type in [None, "raw", "last_action", "full"]:
        for text in [None, "sample text"]:
            res = obs.screenshot.bytes(type=screenshot_type, text=text)  # pyright: ignore [reportArgumentType]
            assert isinstance(res, bytes)
            decoded = res[offset].decode().strip()
            assert decoded == "JFIF"

    ## remote
    with client.Session(headless=True) as session:
        _ = session.execute(dict(type="goto", url="https://linkedin.com"))
        obs = session.observe()

    for screenshot_type in [None, "raw", "last_action", "full"]:
        for text in [None, "sample text"]:
            res = obs.screenshot.bytes(type=screenshot_type, text=text)  # pyright: ignore [reportArgumentType]
            assert isinstance(res, bytes)
            decoded = res[offset].decode().strip()
            assert decoded == "JFIF"


def test_replay_frame_counts() -> None:
    """Test that replays contain the expected number of frames for different scenarios."""
    client = NotteClient()

    with client.Session(headless=True, screenshot_type="last_action") as session:
        _ = session.execute(dict(type="goto", url="https://linkedin.com"))

        img = Image.open(io.BytesIO(session.replay().replay))
        assert img.n_frames == 2  # pyright: ignore [reportUnknownMemberType, reportAttributeAccessIssue]

        agent = client.Agent(session=session, max_steps=1)
        _ = agent.run(task="go to google images, scroll down dog pictures infinitely")

        session_replay_img = Image.open(io.BytesIO(session.replay().replay))
        assert session_replay_img.n_frames == 4  # pyright: ignore [reportUnknownMemberType, reportAttributeAccessIssue]

        agent_replay_img = Image.open(io.BytesIO(agent.replay().replay))
        assert agent_replay_img.n_frames == 3  # pyright: ignore [reportUnknownMemberType, reportAttributeAccessIssue]

        _ = session.execute(dict(type="goto", url="https://duckduckgo.com"))
        session_pre_end_img = Image.open(io.BytesIO(session.replay().replay))
        assert session_pre_end_img.n_frames == 5  # pyright: ignore [reportUnknownMemberType, reportAttributeAccessIssue]

        _ = session.execute(dict(type="goto", url="https://qwant.com"))

    session_end_img = Image.open(io.BytesIO(session.replay().replay))
    assert session_end_img.n_frames == 6  # pyright: ignore [reportUnknownMemberType, reportAttributeAccessIssue]


def test_replay_frame_counts_local() -> None:
    """Test that replays contain the expected number of frames for different scenarios (local version)."""
    notte = NotteClient()

    with notte.Session(headless=True, screenshot_type="last_action") as session:
        _ = session.execute(dict(type="goto", url="https://linkedin.com"))

        img = Image.open(io.BytesIO(session.replay().replay))
        assert img.n_frames == 2  # pyright: ignore [reportUnknownMemberType, reportAttributeAccessIssue]

        agent = notte.Agent(session=session, max_steps=1)
        _ = agent.run(task="go to google images, scroll down dog pictures infinitely")

        session_replay_img = Image.open(io.BytesIO(session.replay().replay))
        assert session_replay_img.n_frames == 4  # pyright: ignore [reportUnknownMemberType, reportAttributeAccessIssue]

        agent_replay_img = Image.open(io.BytesIO(agent.replay().replay))
        assert agent_replay_img.n_frames == 3  # pyright: ignore [reportUnknownMemberType, reportAttributeAccessIssue]

        _ = session.execute(dict(type="goto", url="https://duckduckgo.com"))
        session_pre_end_img = Image.open(io.BytesIO(session.replay().replay))
        assert session_pre_end_img.n_frames == 5  # pyright: ignore [reportUnknownMemberType, reportAttributeAccessIssue]

        _ = session.execute(dict(type="goto", url="https://qwant.com"))

    session_end_img = Image.open(io.BytesIO(session.replay().replay))
    assert session_end_img.n_frames == 6  # pyright: ignore [reportUnknownMemberType, reportAttributeAccessIssue]
