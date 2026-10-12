from notte_sdk import NotteClient

import notte


def test_sdk_screenshots():
    """Make sure everything is in bytes (and not base64 encoded), all in JPEG"""
    client = NotteClient()

    offset = slice(6, 10)

    ## local
    with notte.Session(headless=True) as session:
        _ = session.execute(dict(type="goto", url="https://linkedin.com"))
        obs = session.observe()

    for res in (obs.screenshot.bytes(), obs.screenshot.highlighted()):
        assert isinstance(res, bytes)
        assert res[offset].decode().strip() == "JFIF"

    ## remote
    with client.Session(proxies=False, open_viewer=False) as session:
        _ = session.execute(dict(type="goto", url="https://linkedin.com"))
        obs = session.observe()

    for res in (obs.screenshot.bytes(), obs.screenshot.highlighted()):
        assert isinstance(res, bytes)
        assert res[offset].decode().strip() == "JFIF"
