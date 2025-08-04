import socket
from urllib.parse import urlparse

import requests
import tldextract


def clean_url(url: str) -> str:
    # remove anything after ? i.. ?tfs=CBwQARooEgoyMDI0LTEyLTAzagwIAh
    # remove trailing slash
    # remove https://, http://, www.
    base = url.split("?")[0]
    if base.endswith("/"):
        base = base[:-1]
    base = base.replace("https://", "").replace("http://", "")
    base = base.replace("www.", "")
    return base


def resolve_domain_to_url(domain: str) -> str | None:
    """Resolve a domain to its corresponding URL.

    Args:
        domain (str): The domain to resolve.

    Returns:
        str | None: The corresponding URL if resolved, None otherwise.
    """
    try:
        # Get the IP address of the domain
        _ = socket.gethostbyname(domain)

        # Construct the URL
        url = f"https://{domain}/"
        return url
    except socket.gaierror:
        return None


def is_valid_url(url: str, check_reachability: bool = True) -> bool:
    """Check if the given URL is valid and points to a website.

    Args:
        url (str): The URL to check.

    Returns:
        bool: True if the URL is valid and reachable, False otherwise.
    """
    try:
        # Parse the URL to ensure it has a valid scheme
        parsed_url = urlparse(url)
        if parsed_url.scheme not in ["http", "https", "file"]:
            return False

        if not check_reachability:
            return True
        # Send a HEAD request to the URL
        response = requests.head(url, allow_redirects=True)
        return response.status_code < 400  # Valid if status code is less than 400
    except requests.RequestException:
        return False


def get_root_domain(url: str) -> str:
    """Get the root domain of a URL.

    Args:
        str: The root domain extracted from the URL (e.g., "example.com" from "https://www.example.com/path").
        Returns an empty string for malformed URLs that start with a dot.

    Returns:
        the root domain of the URL
    """
    extracted = tldextract.extract(url)
    if len(extracted.domain) == 0:
        return ""
    extracted = ".".join((extracted.domain, extracted.suffix))
    if extracted[-1] == ".":
        return extracted[:-1]
    return extracted
