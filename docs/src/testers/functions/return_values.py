# @sniptest filename=return_values.py
from pydantic import BaseModel


# Return string
def run_string():
    return "Task completed successfully"


# Return dict
def run_dict():
    extracted_data = ["item1", "item2"]
    return {"status": "success", "data": extracted_data, "count": len(extracted_data)}


# Return list
def run_list():
    return ["item1", "item2", "item3"]


# Return Pydantic model (serialized)
class Result(BaseModel):
    success: bool
    data: list[str]


def run():
    return Result(success=True, data=["a", "b"]).model_dump()
