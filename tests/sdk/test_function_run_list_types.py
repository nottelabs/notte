import datetime as dt

from notte_sdk.types import FunctionRunListItemResponse, ListFunctionRunsResponse


def test_function_run_list_uses_lightweight_items() -> None:
    response = ListFunctionRunsResponse.model_validate(
        {
            "items": [
                {
                    "function_id": "function-1",
                    "function_run_id": "run-1",
                    "created_at": "2026-08-17T10:00:00Z",
                    "updated_at": "2026-08-17T10:01:00Z",
                    "status": "closed",
                    "session_id": None,
                    "local": False,
                }
            ],
            "page": 1,
            "page_size": 10,
            "has_next": False,
            "has_previous": False,
        }
    )

    item = response.items[0]
    assert isinstance(item, FunctionRunListItemResponse)
    assert item.created_at == dt.datetime(2026, 8, 17, 10, tzinfo=dt.UTC)
    assert item.workflow_id == "function-1"
    assert item.workflow_run_id == "run-1"
    assert "logs" not in item.model_dump()
    assert "variables" not in item.model_dump()
    assert "result" not in item.model_dump()
