from app.utils.url import is_same_host, normalize_url, resolve_url


def test_normalize_url_strips_fragment_and_trailing_slash():
    assert normalize_url("https://Example.com/path/#section") == "https://example.com/path"


def test_resolve_url_internal():
    assert resolve_url("https://example.com/a", "/b") == "https://example.com/b"


def test_same_host():
    assert is_same_host("https://example.com/a", "https://example.com/b")
    assert not is_same_host("https://example.com", "https://other.com")
