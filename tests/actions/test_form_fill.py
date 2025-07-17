import glob
import os

import pytest
from notte_browser.form_filling import FormFiller
from notte_core.actions import WaitAction
from patchright.async_api import Locator

import notte


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
    async with notte.Session(
        headless=True, enable_perception=False, viewport_width=1280, viewport_height=720
    ) as session:
        file_path = f"tests/data/checkout/{checkout_file}"
        _ = await session.window.page.goto(url=f"file://{os.path.abspath(file_path)}")

        res = await session.astep(WaitAction(time_ms=100))
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
            assert isinstance(value, Locator), f"Locator for {key} should be a Locator, but got {value}"

            # For select elements, get the display text instead of value
            tag_name = await value.evaluate("el => el.tagName.toLowerCase()")
            if tag_name == "select":
                selected_option = await value.evaluate("el => el.options[el.selectedIndex].text")
                assert selected_option == values[key], f"Value for {key} should be {values[key]}, got {selected_option}"
            else:
                input_value = await value.input_value()
                assert input_value == values[key], f"Value for {key} should be {values[key]}, got {input_value}"
