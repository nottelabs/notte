import glob
import os

import pytest
from notte_browser.form_filling import FormFiller
from notte_core.actions import WaitAction
from notte_core.actions.actions import FormFillAction
from patchright.async_api import Locator

import notte


def test_form_fill_action_strips_null_values():
    """Gemini returns null for unused fields — FormFillAction must strip them."""
    action = FormFillAction(
        value={
            "title": None,
            "first_name": None,
            "email": "lucas@notte.cc",
            "password": "123456",
            "city": None,
        },
    )
    assert action.value == {"email": "lucas@notte.cc", "current_password": "123456"}


def test_form_fill_action_all_null_raises():
    """If all values are null, FormFillAction should raise (min_length=1)."""
    with pytest.raises(Exception):
        FormFillAction(value={"title": None, "email": None})


def get_checkout_files() -> list[str]:
    """Get all HTML files from the checkout folder at runtime."""
    checkout_dir = "tests/data/checkout"
    pattern = os.path.join(checkout_dir, "*.html")
    files = glob.glob(pattern)
    # Return just the filenames, not full paths
    return [os.path.basename(f) for f in files]


@pytest.mark.parametrize("checkout_file", get_checkout_files())
@pytest.mark.asyncio
async def test_form_fill(checkout_file: str):
    async with notte.Session(headless=True, viewport_width=1280, viewport_height=720) as session:
        file_path = f"tests/data/checkout/{checkout_file}"
        _ = await session.window.page.goto(url=f"file://{os.path.abspath(file_path)}")

        res = await session.aexecute(WaitAction(time_ms=100))
        assert res.success
        _ = await session.aobserve()

        values = {
            "first_name": "John",
            "last_name": "Doe",
            "address1": "326 Hurley St",
            "postal_code": "02141",
            "city": "Cambridge",
            "state": "Massachusetts",
            "phone": "(201) 635-1196",
        }
        if checkout_file not in {"crate_and_barrel.html", "joybird.html"}:
            values["email"] = "john.doe@example.com"

        form_filler = FormFiller(session.window.page)
        results = await form_filler.fill_form(values)

        for key, value in results.items():
            # dont check full name, its made up of first and last
            if key == "full_name":
                continue

            assert isinstance(value, Locator), f"Locator for {key} should be a Locator, but got {value}"

            # For select elements, get the display text instead of value
            tag_name = await value.evaluate("el => el.tagName.toLowerCase()")
            if tag_name == "select":
                selected_option = await value.evaluate("el => el.options[el.selectedIndex].text")
                assert selected_option == values[key], f"Value for {key} should be {values[key]}, got {selected_option}"
            else:
                input_value = await value.input_value()
                assert input_value == values[key], f"Value for {key} should be {values[key]}, got {input_value}"


@pytest.mark.asyncio
async def test_form_fill_fails_when_no_field_is_filled():
    async with notte.Session(headless=True) as session:
        await session.window.page.set_content("<html><body><p>No form on this page</p></body></html>")

        res = await session.aexecute(
            FormFillAction(value={"email": "john.doe@example.com", "city": "Cambridge"}), raise_on_failure=False
        )

        assert not res.success
        assert res.message is not None and "no form field could be filled" in res.message


@pytest.mark.asyncio
async def test_form_fill_finds_field_through_aria_labelledby():
    async with notte.Session(headless=True) as session:
        await session.window.page.set_content(
            '<html><body><div><label id="lbl-city">City</label></div><div><input aria-labelledby="lbl-city"></div></body></html>'
        )

        res = await session.aexecute(FormFillAction(value={"city": "Cambridge"}), raise_on_failure=True)

        assert res.success
        assert await session.window.page.locator("input").input_value() == "Cambridge"
