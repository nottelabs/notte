"""Reveal-type cases for scrape overload resolution (checked by basedpyright and ty).

Keep this file free of runtime side effects; checkers only need the annotations.
"""

from __future__ import annotations

from typing import reveal_type

from notte_browser.session import NotteSession
from notte_sdk import NotteClient
from notte_sdk.endpoints.page import PageClient
from notte_sdk.endpoints.sessions import RemoteSession
from pydantic import BaseModel


class Profile(BaseModel):
    name: str


def _check_remote_session(session: RemoteSession) -> None:
    response_format = session.scrape(response_format=Profile, instructions="extract profile")
    reveal_type(response_format)
    instructions = session.scrape(instructions="extract profile")
    reveal_type(instructions)
    images = session.scrape(only_images=True)
    reveal_type(images)
    markdown = session.scrape()
    reveal_type(markdown)
    markdown_params = session.scrape(only_main_content=True)
    reveal_type(markdown_params)
    wrapped = session.scrape(response_format=Profile, raise_on_failure=False)
    reveal_type(wrapped)


def _check_client(client: NotteClient) -> None:
    response_format = client.scrape("https://example.com", response_format=Profile)
    reveal_type(response_format)
    instructions = client.scrape("https://example.com", instructions="extract")
    reveal_type(instructions)
    images = client.scrape("https://example.com", only_images=True)
    reveal_type(images)
    markdown = client.scrape("https://example.com")
    reveal_type(markdown)


def _check_page(page: PageClient) -> None:
    response_format = page.scrape("session-id", response_format=Profile)
    reveal_type(response_format)
    instructions = page.scrape("session-id", instructions="extract")
    reveal_type(instructions)
    images = page.scrape("session-id", only_images=True)
    reveal_type(images)
    markdown = page.scrape("session-id")
    reveal_type(markdown)


def _check_local_session(session: NotteSession) -> None:
    response_format = session.scrape(response_format=Profile, instructions="extract profile")
    reveal_type(response_format)
    instructions = session.scrape(instructions="extract profile")
    reveal_type(instructions)
    images = session.scrape(only_images=True)
    reveal_type(images)
    markdown = session.scrape()
    reveal_type(markdown)
