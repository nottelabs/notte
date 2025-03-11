import re
from typing import Any, Literal
from uuid import uuid4

from loguru import logger
from patchright.async_api import ProxySettings
from typing_extensions import override

from notte.browser.pool.base import BrowserWithContexts
from notte.browser.pool.cdp_pool import BrowserEnum, CDPBrowserPool, CDPSession

try:
    import base64
    import subprocess
    from pathlib import Path

    import orjson
    from camoufox.pkgman import INSTALL_DIR
    from camoufox.server import LAUNCH_SCRIPT, get_nodejs, to_camel_case_dict
    from camoufox.utils import launch_options

except ImportError:
    raise ImportError("Install with notte[camoufox] to include browserbase integration")


def launch_background_camoufox_server(
    headless: bool | Literal["virtual"], geoip: bool, proxy: ProxySettings | None = None, **kwargs: dict[str, Any]
) -> tuple[subprocess.Popen[str], str]:
    """
    Pretty finnicky way to start a camoufox server using the packed nodejs
    and return the websocket address
    """

    # this installs camoufox if it's not installed
    config = launch_options(
        headless=headless,  # type: ignore
        geoip=geoip,
        proxy=proxy,  # type: ignore
        **kwargs,  # type: ignore
    )

    config_path = INSTALL_DIR / "camoufox.cfg"
    if not config_path.is_file():
        raise ValueError("Camoufox was not installed")

    # replace uBO list, adding cookie notice blocking from easylist
    default_config = config_path.read_text()
    _ = config_path.write_text(
        default_config.replace(
            "https://raw.githubusercontent.com/daijro/camoufox/refs/heads/main/assets/uBOAssets.json",
            "https://raw.githubusercontent.com/leo-notte/camoufox/refs/heads/main/assets/uBOAssets.json",
        )
    )

    nodejs = get_nodejs()

    data = orjson.dumps(to_camel_case_dict(config))

    args = [
        nodejs,
        str(LAUNCH_SCRIPT),
    ]

    process = subprocess.Popen(
        args,  # nosec
        cwd=Path(nodejs).parent / "package",
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=1,  # Line buffered
        universal_newlines=True,  # Text mode
    )

    # Write the input data
    assert process.stdin is not None
    _ = process.stdin.write(base64.b64encode(data).decode())
    process.stdin.flush()
    process.stdin.close()

    assert process.stdout is not None
    # Read output in real-time
    lines = 3
    output: str = ""
    while lines > 0:
        output = process.stdout.readline()
        lines -= 1

    match = re.search(r"wss?:\/\/[a-zA-Z0-9.-]+(?::\d+)?(?:\/[^\s]*)?", output)
    if match:
        return process, match.group(0)

    raise ValueError(f"No websocket addr in {output}")


# TODO: integrate as local pool instead at some point?
class CamoufoxPool(CDPBrowserPool):
    def __init__(
        self,
        verbose: bool = False,
    ):
        super().__init__(verbose=verbose)

    @property
    @override
    def browser_type(self) -> BrowserEnum:
        return BrowserEnum.FIREFOX

    @override
    def create_session_cdp(self, proxy: ProxySettings | None = None) -> CDPSession:
        if self.verbose:
            logger.info("Creating Camoufox session...")

        _, addr = launch_background_camoufox_server(headless="virtual", geoip=True, proxy=proxy)

        return CDPSession(
            session_id=str(uuid4()),
            cdp_url=addr,
        )

    @override
    async def close_playwright_browser(self, browser: BrowserWithContexts, force: bool = True) -> bool:
        if self.verbose:
            logger.info(f"Closing CDP session for URL {browser.cdp_url}")
        await browser.browser.close()
        del self.sessions[browser.browser_id]
        return True
