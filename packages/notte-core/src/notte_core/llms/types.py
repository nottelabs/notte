from typing import TypeVar

from pydantic import BaseModel

TResponseFormat = TypeVar("TResponseFormat", bound=BaseModel)
