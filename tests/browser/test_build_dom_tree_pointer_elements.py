import notte


def test_pointer_elements_on_hover():
    with notte.Session() as session:
        _ = session.execute({"type": "goto", "url": "https://www.verizon.com/expresspay/#/auth"})
        _ = session.execute({"type": "click", "selector": 'internal:text="Account no. and billing zip"i'})
        _ = session.execute(
            {"type": "fill", "selector": 'internal:role=textbox[name="Account Number"i]', "value": "556989104000174"}
        )
        _ = session.execute({"type": "fill", "selector": 'internal:role=textbox[name="00000"i]', "value": "11385"})
        _ = session.execute({"type": "click", "selector": 'internal:role=button[name="Continue"i]'})
        _ = session.execute({"type": "click", "selector": 'internal:role=link[name="Pay My Bill "i]'})
        _ = session.execute({"type": "fill", "selector": 'internal:role=textbox[name="0.00"i]', "value": "10.00"})
        _ = session.execute(
            {
                "type": "click",
                "selector": 'laf-dropdown div >> internal:has-text="Select Payment Method Select"i >> div',
            }
        )
        _ = session.observe()
        node = session.snapshot.dom_node.find("M3")
        assert node is not None
        assert node.text == "Select Payment Method"
        assert node.parent is not None
        assert len(node.parent.children) == 2
        sub_menu = node.parent.children[-1]
        hover_menu_nodes = sub_menu.interaction_nodes()
        assert len(hover_menu_nodes) == 5
        assert [node.text for node in hover_menu_nodes] == [
            "Checking",
            "Savings",
            "Debit",
            "Credit",
            "Verizon Gift Card",
        ]
