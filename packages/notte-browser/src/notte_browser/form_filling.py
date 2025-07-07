import asyncio
import random

from loguru import logger
from patchright.async_api import Locator, Page


def escape_css_selector(selector: str) -> str:
    """
    Escape special characters in CSS selectors.
    This is a simplified version of CSS.escape() for common cases.
    """
    # Handle special characters that need escaping in CSS selectors
    special_chars = ":._-[]#()"
    result = ""
    for char in selector:
        if char in special_chars:
            result += f"\\{char}"
        else:
            result += char
    return result


class FormFiller:
    # Common field names and identifiers for all form types
    FIELD_SELECTORS: dict[str, list[str]] = {
        # Identity Fields
        "title": [
            '[autocomplete="honorific-prefix"]',
            '[name*="title"]',
            '[id*="title"]',
            '[name*="prefix"]',
            '[id*="prefix"]',
            # German
            '[name*="anrede"]',
            '[id*="anrede"]',
        ],
        "first_name": [
            '[autocomplete*="given-name"]',
            '[name*="first"][name*="name"]',
            '[id*="first"][id*="name"]',
            '[name*="firstname"]',
            '[id*="firstname"]',
            'input[placeholder*="First"]',
            # German
            '[name*="vorname"]',
            '[id*="vorname"]',
        ],
        "middle_name": [
            '[autocomplete="additional-name"]',
            '[name*="middle"][name*="name"]',
            '[id*="middle"][id*="name"]',
            '[name*="middlename"]',
            '[id*="middlename"]',
        ],
        "last_name": [
            '[autocomplete*="family-name"]',
            '[name*="last"][name*="name"]',
            '[id*="last"][id*="name"]',
            '[name*="lastname"]',
            '[id*="lastname"]',
            'input[placeholder*="Last"]',
            # German
            '[name*="nachname"]',
            '[id*="nachname"]',
        ],
        "email": [
            '[autocomplete="email"]',
            'input[type="email"]',
            '[name*="email"]',
            '[id*="email"]',
            'input[placeholder*="email" i]',
        ],
        "company": [
            '[autocomplete="organization"]',
            '[name*="company"]',
            '[id*="company"]',
            '[name*="organization"]',
            '[id*="organization"]',
            # German
            '[name*="firma"]',
            '[id*="firma"]',
        ],
        "address1": [
            '[autocomplete="street-address"]',
            '[autocomplete="address-line1"]',
            '[name*="address"][name*="1"]',
            '[id*="address"][id*="1"]',
            '[name*="street"]',
            '[id*="street"]',
            # German
            '[name*="strasse"]',
            '[id*="strasse"]',
        ],
        "address2": [
            '[autocomplete="address-line2"]',
            '[name*="address"][name*="2"]',
            '[id*="address"][id*="2"]',
            '[name*="suite"]',
            '[id*="suite"]',
            '[name*="apt"]',
            '[id*="apt"]',
        ],
        "address3": [
            '[autocomplete="address-line3"]',
            '[name*="address"][name*="3"]',
            '[id*="address"][id*="3"]',
        ],
        "city": [
            '[autocomplete="address-level2"]',
            '[name*="city"]',
            '[id*="city"]',
            '[name*="town"]',
            '[id*="town"]',
            # German
            '[name*="ort"]',
            '[id*="ort"]',
            '[name*="stadt"]',
            '[id*="stadt"]',
        ],
        "state": [
            '[autocomplete="address-level1"]',
            'select[name*="state"]',
            'select[id*="state"]',
            '[name*="state"]',
            '[id*="state"]',
            'select[name*="province"]',
            'select[id*="province"]',
            '[name*="province"]',
            '[id*="province"]',
            # German
            'select[name*="bundesland"]',
            'select[id*="bundesland"]',
            '[name*="bundesland"]',
            '[id*="bundesland"]',
        ],
        "postal_code": [
            '[autocomplete="postal-code"]',
            '[name*="zip"]',
            '[id*="zip"]',
            '[name*="postal"]',
            '[id*="postal"]',
            # German
            '[name*="plz"]',
            '[id*="plz"]',
        ],
        "country": [
            '[autocomplete="country"]',
            '[autocomplete="country-name"]',
            'select[name*="country"]',
            'select[id*="country"]',
            '[name*="country"]',
            '[id*="country"]',
            # German
            'select[name*="land"]',
            'select[id*="land"]',
            '[name*="land"]',
            '[id*="land"]',
        ],
        "phone": [
            '[autocomplete="tel"]',
            'input[type="tel"]',
            '[name*="phone"]',
            '[id*="phone"]',
            '[name*="mobile"]',
            '[id*="mobile"]',
            # German
            '[name*="telefon"]',
            '[id*="telefon"]',
            '[name*="handy"]',
            '[id*="handy"]',
        ],
        # Credit Card Fields
        "cc_name": [
            '[autocomplete="cc-name"]',
            '[name*="card"][name*="name"]',
            '[id*="card"][id*="name"]',
            '[name*="cardholder"]',
            '[id*="cardholder"]',
        ],
        "cc_number": [
            '[autocomplete="cc-number"]',
            'input[type="credit-card"]',
            '[name*="card"][name*="number"]',
            '[id*="card"][id*="number"]',
            '[name*="cardnumber"]',
            '[id*="cardnumber"]',
        ],
        "cc_exp_month": [
            '[autocomplete="cc-exp-month"]',
            '[name*="exp"][name*="month"]',
            '[id*="exp"][id*="month"]',
            '[name*="expmonth"]',
            '[id*="expmonth"]',
        ],
        "cc_exp_year": [
            '[autocomplete="cc-exp-year"]',
            '[name*="exp"][name*="year"]',
            '[id*="exp"][id*="year"]',
            '[name*="expyear"]',
            '[id*="expyear"]',
        ],
        "cc_exp": [
            '[autocomplete="cc-exp"]',
            '[name*="expiration"]',
            '[id*="expiration"]',
            '[name*="exp-date"]',
            '[id*="exp-date"]',
        ],
        "cc_cvv": [
            '[autocomplete="cc-csc"]',
            '[name*="cvv"]',
            '[id*="cvv"]',
            '[name*="cvc"]',
            '[id*="cvc"]',
            '[name*="security"][name*="code"]',
            '[id*="security"][id*="code"]',
        ],
        # Login/Password Fields
        "username": [
            '[autocomplete="username"]',
            'input[type="email"]',
            '[name*="user"][name*="name"]',
            '[id*="user"][id*="name"]',
            '[name*="login"]',
            '[id*="login"]',
            '[name*="email"]',
            '[id*="email"]',
        ],
        "current_password": [
            '[autocomplete="current-password"]',
            'input[type="password"]',
            '[name*="current"][name*="password"]',
            '[id*="current"][id*="password"]',
            '[name*="old"][name*="password"]',
            '[id*="old"][id*="password"]',
        ],
        "new_password": [
            '[autocomplete="new-password"]',
            '[name*="new"][name*="password"]',
            '[id*="new"][id*="password"]',
            '[name*="create"][name*="password"]',
            '[id*="create"][id*="password"]',
        ],
        "totp": [
            '[autocomplete="one-time-code"]',
            '[name*="totp"]',
            '[id*="totp"]',
            '[name*="2fa"]',
            '[id*="2fa"]',
            '[name*="mfa"]',
            '[id*="mfa"]',
            'input[placeholder*="verification code" i]',
        ],
    }

    def __init__(self, page: Page):
        """Initialize the FormFiller with a Playwright page."""
        self.page: Page = page
        self._found_fields: dict[str, Locator] = {}

    async def find_field(self, field_type: str) -> Locator | None:
        """Find a field by trying multiple selectors."""
        if field_type not in self.FIELD_SELECTORS:
            return None

        # Check cache first
        if field_type in self._found_fields:
            return self._found_fields[field_type]

        # Try each selector until we find a match
        for selector in self.FIELD_SELECTORS[field_type]:
            try:
                # First try exact selector
                locator = self.page.locator(selector)
                if await locator.count() > 0:
                    # For select elements, verify they have options
                    if "select" in selector:
                        options = locator.first.locator("option")
                        if await options.count() > 0:
                            self._found_fields[field_type] = locator.first
                            return self._found_fields[field_type]
                    else:
                        self._found_fields[field_type] = locator.first
                        return self._found_fields[field_type]
            except Exception as e:
                logger.warning(f"Warning: Invalid selector {selector}: {str(e)}")
                continue

        # Try finding by label text
        try:
            labels = self.page.locator("label")
            count = await labels.count()

            for i in range(count):
                label = labels.nth(i)
                label_text = await label.text_content()
                if not label_text:
                    continue

                label_text = label_text.lower()
                if field_type.replace("_", " ") in label_text:
                    # Try to find the associated input or select
                    for_attr = await label.get_attribute("for")
                    if for_attr:
                        try:
                            # Try different strategies to find the input/select
                            escaped_id = escape_css_selector(for_attr)

                            # Try both input and select elements
                            for element_type in ["input", "select"]:
                                # Try by ID with proper escaping
                                field = self.page.locator(f"{element_type}#{escaped_id}")
                                if await field.count() > 0:
                                    self._found_fields[field_type] = field.first
                                    return self._found_fields[field_type]

                                # Try by exact attribute match
                                field = self.page.locator(f'{element_type}[id="{for_attr}"]')
                                if await field.count() > 0:
                                    self._found_fields[field_type] = field.first
                                    return self._found_fields[field_type]

                                # Try by name attribute
                                field = self.page.locator(f'{element_type}[name="{for_attr}"]')
                                if await field.count() > 0:
                                    self._found_fields[field_type] = field.first
                                    return self._found_fields[field_type]

                        except Exception as e:
                            logger.error(f"Warning: Failed to find field for label with for={for_attr}: {str(e)}")
                            continue

                    # If no 'for' attribute or not found, try finding the field as a child or sibling
                    try:
                        # Try finding any input/select related to this label
                        related_fields = [
                            label.locator("input, select"),  # Child elements
                            label.locator("+ input, + select"),  # Next siblings
                            label.locator("~ input, ~ select"),  # Any following siblings
                            self.page.locator(
                                f'input[aria-labelledby="{label.get_attribute("id")}"], select[aria-labelledby="{label.get_attribute("id")}"]'
                            ),  # ARIA relationship
                        ]

                        for field in related_fields:
                            if await field.count() > 0:
                                self._found_fields[field_type] = field.first
                                return self._found_fields[field_type]

                    except Exception as e:
                        logger.error(f"Warning: Failed to find related field for label: {str(e)}")
                        continue

        except Exception as e:
            logger.error(f"Warning: Error while searching by label: {str(e)}")

        return None

    async def fill_form(self, data: dict[str, str]) -> None:
        """
        Fill form fields with the provided data.

        Args:
            data: Dictionary containing form data with keys matching FIELD_SELECTORS
        """

        filled_count = 0
        failed_fields: list[str] = []

        # Randomize the order of fields to make form filling more human-like
        field_types = list(data.keys())
        random.shuffle(field_types)

        for field_type in field_types:
            value = data[field_type]
            if not value:  # Skip empty values
                continue

            field = await self.find_field(field_type)
            if field:
                tag_name: str = await field.evaluate("el => el.tagName.toLowerCase()")
                try:
                    # Check if it's a select element
                    if tag_name == "select":
                        # Try exact match first
                        _ = await field.select_option(value=value)
                    else:
                        await field.click()
                        await asyncio.sleep(random.uniform(0.1, 0.3))
                        await field.clear()
                        await asyncio.sleep(random.uniform(0.1, 0.3))
                        await field.press_sequentially(value, delay=random.uniform(50, 150))
                    logger.debug(f"Successfully filled {field_type} field")
                    filled_count += 1
                    await asyncio.sleep(random.uniform(0.1, 0.5))

                except Exception as e:
                    try:
                        # If exact match fails for select, try case-insensitive match
                        if tag_name == "select":
                            # Get all options
                            options: list[dict[str, str]] = await field.evaluate("""select => {
                                return Array.from(select.options).map(option => ({
                                    value: option.value,
                                    text: option.text
                                }));
                            }""")

                            # Try to find a matching option
                            target_value: str = value.lower()
                            for option in options:
                                lower_value: str = option["value"].lower()
                                lower_text: str = option["text"].lower()
                                if lower_value == target_value or lower_text == target_value:
                                    _ = await field.select_option(value=option["value"])
                                    logger.debug(f"Successfully filled {field_type} field (case-insensitive match)")
                                    filled_count += 1

                                    # Add a random wait between 100ms and 500ms
                                    await asyncio.sleep(random.uniform(0.5, 1.5))

                                    break
                            else:
                                logger.warning(f"Failed to fill {field_type} field: No matching option found")
                                failed_fields.append(field_type)
                        else:
                            logger.warning(f"Failed to fill {field_type} field {str(e)}")
                            failed_fields.append(field_type)
                    except Exception as e2:
                        logger.warning(f"Failed to fill {field_type} field (both attempts) {str(e2)}")
                        failed_fields.append(field_type)
                else:
                    logger.debug(f"Field {field_type} not found on page")
            logger.info(f"Form filling completed: {filled_count} fields filled, {len(failed_fields)} failed")

    async def get_found_fields(self) -> dict[str, bool]:
        """
        Return a dictionary indicating which fields were found on the page.

        Returns:
            Dict mapping field types to boolean indicating if they were found.
        """
        return {field_type: bool(await self.find_field(field_type)) for field_type in self.FIELD_SELECTORS.keys()}
