from notte_browser.dom.id_generation import generate_sequential_ids
from notte_browser.dom.types import DOMBaseNode, DOMElementNode


def make_node(
    tag_name: str, xpath: str | None = None, children: list[DOMBaseNode] | None = None, interactive: bool = True
) -> DOMElementNode:
    node = DOMElementNode(
        tag_name=tag_name,
        xpath=xpath or "//test",
        in_iframe=False,
        in_shadow_root=False,
        css_path="test",
        iframe_parent_css_selectors=[],
        notte_selector="test",
        attributes={},
        is_visible=True,
        is_interactive=interactive,
        is_top_element=True,
        is_editable=False,
        highlight_index=0 if interactive else None,
        bbox=None,
        shadow_root=False,
        parent=None,
    )
    node.children = children or []
    return node


def test_basic_id_generation_works():
    """Test that basic ID generation works with current implementation."""
    # Create a simple interactive node
    button = make_node("button", xpath="//button[@id='test']")
    root = make_node("div", xpath="//div", interactive=False)
    root.children = [button]

    # This should work with current implementation
    _ = generate_sequential_ids(root, url="https://test.com")

    # Should have generated an ID
    assert button.notte_id is not None
    assert button.notte_id.startswith("B")  # Current implementation uses "B" for buttons


def test_same_xpath_same_id_across_snapshots():
    """Test that elements with same XPath get same IDs across snapshots of same base URL."""
    url = "https://example.com/page"
    xpath = "//button[@id='submit']"

    # First snapshot
    button1 = make_node("button", xpath=xpath)
    root1 = make_node("div", xpath="//div", interactive=False)
    root1.children = [button1]

    # This will fail because current implementation doesn't accept url parameter
    # and doesn't maintain ID consistency based on XPath
    _ = generate_sequential_ids(root1, url=url)
    first_id = button1.notte_id
    assert first_id is not None

    # Second snapshot (same URL)
    button2 = make_node("button", xpath=xpath)
    root2 = make_node("div", xpath="//div", interactive=False)
    root2.children = [button2]

    _ = generate_sequential_ids(root2, url=url)
    # This will fail because current implementation doesn't maintain IDs across snapshots
    assert button2.notte_id == first_id, "Same XPath elements should get same IDs across snapshots"


def test_different_urls_different_counters():
    """Test that different base URLs maintain separate ID counters."""
    url1 = "https://example.com/page1"
    url2 = "https://example.com/page2"
    xpath = "//button[@id='submit']"

    # First URL
    b1 = make_node("button", xpath=xpath)
    root1 = make_node("div", xpath="//div", interactive=False)
    root1.children = [b1]

    # Will fail because url parameter doesn't exist
    _ = generate_sequential_ids(root1, url=url1)
    assert b1.notte_id == "B1"

    # Second URL - should start fresh counter
    b1_newpage = make_node("button", xpath=xpath)
    root2 = make_node("div", xpath="//div", interactive=False)
    root2.children = [b1_newpage]

    _ = generate_sequential_ids(root2, url=url2)
    # Will fail because current implementation shares counter across all URLs
    assert b1_newpage.notte_id == "B1"


def test_query_params_ignored():
    """Test that query parameters don't affect the base URL matching."""
    base_url = "https://example.com/page4"
    url_with_params = f"{base_url}?param=value"
    xpath = "//button[@id='submit']"

    # First snapshot (base URL)
    button1 = make_node("button", xpath=xpath)
    root1 = make_node("div", xpath="//div", interactive=False)
    root1.children = [button1]

    # Will fail because url parameter doesn't exist
    _ = generate_sequential_ids(root1, url=base_url)
    first_id = button1.notte_id

    # Second snapshot (URL with params)
    button2 = make_node("button", xpath=xpath)
    root2 = make_node("div", xpath="//div", interactive=False)
    root2.children = [button2]

    _ = generate_sequential_ids(root2, url=url_with_params)
    # Will fail because current implementation doesn't handle URLs at all
    assert button2.notte_id == first_id, "Query parameters should not affect ID generation"


def test_xpath_based_id_sequence():
    """Test that ID sequence is maintained correctly for each XPath within a base URL."""
    url = "https://example.com/page5"
    xpath1 = "//button[@id='first']"
    xpath2 = "//button[@id='second']"

    # First snapshot with two different buttons
    button1 = make_node("button", xpath=xpath1)
    button2 = make_node("button", xpath=xpath2)
    root1 = make_node("div", xpath="//div", interactive=False)
    root1.children = [button1, button2]

    # Will fail because url parameter doesn't exist
    _ = generate_sequential_ids(root1, url=url)

    # Second snapshot with same buttons in different order
    new_button2 = make_node("button", xpath=xpath2)
    new_button1 = make_node("button", xpath=xpath1)
    root2 = make_node("div", xpath="//div", interactive=False)
    root2.children = [new_button2, new_button1]  # Different order!

    _ = generate_sequential_ids(root2, url=url)

    # These will fail because current implementation assigns IDs based on traversal order
    # not based on XPath identity
    assert new_button1.notte_id == button1.notte_id, "Same XPath should get same ID regardless of order"
    assert new_button2.notte_id == button2.notte_id, "Same XPath should get same ID regardless of order"


def test_mixed_elements_id_sequencing():
    """Test that adding a new element of the same type in the middle gets the next sequential ID."""
    url = "https://example.com/page6"

    # Create initial mixed set of elements
    b1 = make_node("button", xpath="//button[@id='submit']")
    l1 = make_node("a", xpath="//a[@id='home']")
    i1 = make_node("input", xpath="//input[@id='email']")
    i2 = make_node("input", xpath="//input[@id='email', @id='email2']")
    b2 = make_node("button", xpath="//button[@id='submit', @id='submit2']")
    b_disabled = make_node("button", xpath="//button[@id='submit', @id='submit3']", interactive=False)

    # Create root with elements in order: button, link, input
    root1 = make_node("div", xpath="//div", interactive=False)
    children = [b1, l1, i1, i2, b2, b_disabled]
    root1.children = children

    # Generate IDs for first snapshot
    _ = generate_sequential_ids(root1, url=url)

    # Record the IDs
    def test_ids():
        assert b1.notte_id == "B1"
        assert l1.notte_id == "L1"
        assert i1.notte_id == "I1"
        assert i2.notte_id == "I2"
        assert b2.notte_id == "B2"
        assert b_disabled.notte_id is None

    test_ids()

    # Now create a new snapshot with a button inserted in the middle
    # Order: button1, link1, NEW_BUTTON, input1
    b3 = make_node("button", xpath="//button[@id='new_button']")  # New button
    i3 = make_node("input", xpath="//input[@id='email_new']")

    root2 = make_node("div", xpath="//div", interactive=False)
    root2.children = [b3, i3, *children]

    # Generate IDs for second snapshot
    _ = generate_sequential_ids(root2, url=url)

    test_ids()
    assert b3.notte_id == "B3"
    assert i3.notte_id == "I3"
