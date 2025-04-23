from notte_core.utils.url import get_root_domain


def test_get_root_domain_with_https():
    """Test get_root_domain with URLs that already have https:// prefix."""
    assert get_root_domain("https://example.com") == "example.com"
    assert get_root_domain("https://www.example.com") == "example.com"
    assert get_root_domain("https://subdomain.example.com") == "example.com"
    assert get_root_domain("https://example.com/path?query=1") == "example.com"


def test_get_root_domain_with_http():
    """Test get_root_domain with URLs that have http:// prefix."""
    assert get_root_domain("http://example.com") == "example.com"
    assert get_root_domain("http://www.example.com") == "example.com"
    assert get_root_domain("http://subdomain.example.com") == "example.com"


def test_get_root_domain_without_protocol():
    """Test get_root_domain with URLs that don't have a protocol prefix."""
    assert get_root_domain("example.com") == "example.com"
    assert get_root_domain("www.example.com") == "example.com"
    assert get_root_domain("subdomain.example.com") == "example.com"
    assert get_root_domain("example.com/path?query=1") == "example.com"


def test_get_root_domain_with_complex_domains():
    """Test get_root_domain with more complex domain structures."""
    assert get_root_domain("example.co.uk") == "example.co.uk"
    assert get_root_domain("subdomain.example.co.uk") == "example.co.uk"
    assert get_root_domain("example.com:8080") == "example.com"
    assert get_root_domain("example.com:8080/path") == "example.com"


def test_get_root_domain_with_ip_addresses():
    """Test get_root_domain with IP addresses."""
    assert get_root_domain("192.168.1.1") == "192.168.1.1"
    assert get_root_domain("https://192.168.1.1") == "192.168.1.1"
    assert get_root_domain("http://192.168.1.1:8080") == "192.168.1.1"


def test_wrong_urls():
    """Test get_root_domain with wrong URLs."""
    assert get_root_domain("invalid-url") == "invalid-url"
    assert get_root_domain("http://") == ""
    assert get_root_domain("https://") == ""
    assert get_root_domain("http://.com") == ""
    assert get_root_domain("https://invalid-url") == "invalid-url"


def test_get_root_domain_with_subdirectory():
    """Test get_root_domain with URL that includes subdirectories."""
    assert get_root_domain("https://app.neo.space/mail/") == "neo.space"
