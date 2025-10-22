"""Common types used across Notte."""

from typing import TypeVar

from pydantic import BaseModel

TResponseFormat = TypeVar("TResponseFormat", bound=BaseModel)
