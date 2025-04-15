from notte_core import check_notte_version

from notte_sdk.client import NotteClient

__version__ = check_notte_version("notte_sdk")

__all__ = ["NotteClient"]
