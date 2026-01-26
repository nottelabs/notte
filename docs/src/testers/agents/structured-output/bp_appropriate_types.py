from datetime import date

from pydantic import BaseModel


class Event(BaseModel):
    title: str
    date: date  # Will be parsed as date
    price: float  # Not str
    attendee_count: int  # Not float
