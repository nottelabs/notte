import pytest
from notte_browser.tagging.action.llm_taging.parser import (
    parse_action_ids,
    parse_action_parameters,
    parse_table,
    parse_table_parameter,
)
from notte_core.actions.percieved import ActionParameter


def test_parse_parameter_no_defaults_values():
    param = parse_table_parameter("name: paramA, type: int")
    assert param.name == "paramA"
    assert param.type == "int"
    assert param.default is None
    assert param.values == []


def test_parse_parameter_empty_values_list():
    param = parse_table_parameter("name: paramB, type: float, values=[]")
    assert param.name == "paramB"
    assert param.type == "float"
    assert param.values == [""]


def test_parse_parameter_quoted_values():
    param = parse_table_parameter('name: paramC, type: string, values=["val1","val2","val3"]')
    assert param.name == "paramC"
    assert param.type == "string"
    assert param.values == ["val1", "val2", "val3"]


def test_parse_parameter_single_value():
    param = parse_table_parameter("name: paramD, type: boolean, default=true")
    assert param.name == "paramD"
    assert param.type == "boolean"
    assert param.default == "true"
    assert param.values == []


def test_parse_table_empty_table():
    table = ""
    with pytest.raises(ValueError) as e:
        _ = parse_table(table)
    assert "Empty table" in str(e.value)


def test_parse_table_invalid_headers():
    table = """
    | Wrong | Headers | For | Table |
    | --- | --- | --- | --- |
    | action_1 | Desc | name: p1, type: int | cat1 |
    """
    with pytest.raises(ValueError) as e:
        _ = parse_table(table)
    assert "Invalid table headers" in str(e.value)


def test_parse_table_invalid_params():
    table = """
    | ID | Description | Parameters | Category |
    | --- | --- | --- | --- |
    | action_1 | Desc | invalid_param_format | cat1 |
    """
    with pytest.raises(ValueError) as e:
        _ = parse_table(table)
        assert "invalid_param_format" in str(e.value)


def action_parameters() -> list[str]:
    return [
        # Settings and Preferences
        " B3: Open accessibility feedback dialog",
        # Search Actions
        " I1: Select ticket type (ticketType: string = [Round trip, One way, Multi-city])",
        " I2: Select seating class (seatingClass: string = [Economy, Premium economy, Business, First])",
        " I3: Enter origin (origin: string = [Boston, New York, Los Angeles, ...])",
        " I6: Enter return date (returnDate: date = [2023-12-01, 2023-12-02, ...])",
        # Flight Search and Booking Actions
        " B8: Explore destinations",
        (
            " B9-17: View more information on suggested flights (suggestion: string "
            "= [New York, Providence, Hartford, Boston, "
            "Paris, Reykjavík, Miami, Barcelona])"
        ),
        " [L1]: Access source page",
        (
            " [L2, L3]: View route (source: string = "
            "[Boston, New York, Los Angeles, ...], "
            "destination: string = [Boston, New York, Los Angeles, ...])"
        ),
        "B26: Change language to English (United States)",
    ]


def action_ids() -> list[list[str]]:
    return [
        ["B3"],
        ["I1"],
        ["I2"],
        ["I3"],
        ["I6"],
        ["B8"],
        ["B9", "B10", "B11", "B12", "B13", "B14", "B15", "B16", "B17"],
        ["L1"],
        ["L2", "L3"],
        ["B26"],
    ]


@pytest.mark.parametrize(
    "action_str, expected_ids",
    zip(action_parameters(), action_ids()),
)
def test_parse_action_ids(action_str: str, expected_ids: list[str]) -> None:
    parsed_id = parse_action_ids(action_str)
    assert parsed_id == expected_ids  # nosec: B101


def action_parameters_with_values() -> list[list[ActionParameter]]:
    return [
        [],
        [
            ActionParameter(
                name="ticketType",
                type="string",
                values=["Round trip", "One way", "Multi-city"],
            ),
        ],
        [
            ActionParameter(
                name="seatingClass",
                type="string",
                values=["Economy", "Premium economy", "Business", "First"],
            ),
        ],
        [
            ActionParameter(
                name="origin",
                type="string",
                values=["Boston", "New York", "Los Angeles", "..."],
            ),
        ],
        [
            ActionParameter(
                name="returnDate",
                type="date",
                values=["2023-12-01", "2023-12-02", "..."],
            ),
        ],
        [],
        [
            ActionParameter(
                name="suggestion",
                type="string",
                values=[
                    "New York",
                    "Providence",
                    "Hartford",
                    "Boston",
                    "Paris",
                    "Reykjavík",
                    "Miami",
                    "Barcelona",
                ],
            ),
        ],
        [],
        [
            ActionParameter(
                name="source",
                type="string",
                values=["Boston", "New York", "Los Angeles", "..."],
            ),
            ActionParameter(
                name="destination",
                type="string",
                values=["Boston", "New York", "Los Angeles", "..."],
            ),
        ],
        [],
    ]


@pytest.mark.parametrize(
    "action_str, expected_parameters",
    zip(action_parameters(), action_parameters_with_values()),
)
def test_parse_action_parameters(action_str: str, expected_parameters: list[ActionParameter]) -> None:
    parsed_parameters = parse_action_parameters(action_str)
    assert parsed_parameters == expected_parameters  # nosec: B101
