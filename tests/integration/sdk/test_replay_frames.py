from notte_sdk import NotteClient


def test_sdk_screenshots_remote():
    client = NotteClient()
    offset = slice(6, 10)

    with client.Session(proxies=False, open_viewer=False) as session:
        _ = session.execute(dict(type="goto", url="https://linkedin.com"))
        obs = session.observe()

    for screenshot_type in [None, "raw", "last_action", "full"]:
        for text in [None, "sample text"]:
            res = obs.screenshot.bytes(type=screenshot_type, text=text)  # pyright: ignore [reportArgumentType]
            assert isinstance(res, bytes)
            decoded = res[offset].decode().strip()
            assert decoded == "JFIF"
