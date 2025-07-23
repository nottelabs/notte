import asyncio
import random

from loguru import logger
from patchright.async_api import Locator, Page

from notte_browser.playwright import PlaywrightLocator


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
        "full_name": [
            '[autocomplete="name"]',
            '[autocomplete="shipping name"]',
            '[data-automation="full-name-input"]',
            '[name="fullName"]',
            '[name*="full"][name*="name"]',
            '[id*="full"][id*="name"]',
            '[autocomplete="name"]',
            'input[placeholder*="Full Name" i]',
            'input[placeholder*="Full name" i]',
        ],
        "email": [
            '[autocomplete="email"]',
            'xpath=//input[@*[contains(name(), "target")] = "emailInput"]',
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
            '[autocomplete="shipping address-line1"]',
            '[name*="address"][name*="1"]',
            '[id*="address"][id*="1"]',
            '[name*="street"]',
            '[id*="street"]',
            '[data-testid*="address1"]',
            '[data-testid*="address-1"]',
            '[data-testid*="shipping-address1"]',
            '[data-testid*="billing-address1"]',
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
            '[autocomplete="shipping address-level2"]',
            '[id*="city"]',
            '[name*="city"]',
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
            '[autocomplete="shipping address-level1"]',
            'select[name*="state"]',
            'select[id*="state"]',
            '[id*="state"]',
            '[name*="state"]',
            'select[name*="province"]',
            'select[id*="province"]',
            '[autocomplete="shipping address-level1"]',
            '[autocomplete="billing address-level1"]',
            '[name="zone"]',
            '[id="zone"]',
            '[name*="state"]',
            '[id*="state"]',
            '[name*="province"]',
            '[id*="province"]',
            '[data-testid*="state"]',
            '[data-testid*="province"]',
            '[data-testid*="zone"]',
            # German
            'select[name*="bundesland"]',
            'select[id*="bundesland"]',
            '[name*="bundesland"]',
            '[id*="bundesland"]',
        ],
        "postal_code": [
            '[autocomplete="postal-code"]',
            '[autocomplete="shipping postal-code"]',
            '[id*="zip"]',
            '[name*="zip"]',
            '[name*="postal"]',
            '[id*="postal"]',
            # German
            '[name*="plz"]',
            '[id*="plz"]',
        ],
        "country": [
            '[autocomplete="country"]',
            '[autocomplete="country-name"]',
            '[autocomplete="shipping country"]',
            '[autocomplete="billing country"]',
            'select[name*="country"]',
            'select[id*="country"]',
            '[name*="country"]',
            '[id*="country"]',
            '[name*="countryCode"]',
            '[id*="countryCode"]',
            '[data-testid*="country"]',
            '[data-testid*="region"]',
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

    async def _detect_name_field_conflicts(self, data: dict[str, str]) -> dict[str, str]:
        """
        Detect and resolve conflicts between individual name fields and full name field.

        Args:
            data: Original form data

        Returns:
            Modified data with name field conflicts resolved
        """
        # Check if we have name-related data
        has_first_name = bool(data.get("first_name"))
        has_last_name = bool(data.get("last_name"))
        has_full_name = bool(data.get("full_name"))

        if not (has_first_name or has_last_name or has_full_name):
            return data

        # Check if full_name field exists on the page
        full_name_field = await self.find_field("full_name")
        # _ = await self.find_field("first_name")
        # _ = await self.find_field("last_name")

        # If full_name field exists and we have individual name data, prioritize full_name
        if full_name_field and (has_first_name or has_last_name):
            # Combine first and last name for full_name field
            first_name = data.get("first_name", "").strip()
            last_name = data.get("last_name", "").strip()

            if first_name and last_name:
                combined_name = f"{first_name} {last_name}"
            elif first_name:
                combined_name = first_name
            elif last_name:
                combined_name = last_name
            else:
                combined_name = ""

            # Check if the combined name would fit within maxlength constraints
            maxlength_attr = await full_name_field.get_attribute("maxlength")
            if maxlength_attr:
                try:
                    maxlength = int(maxlength_attr)
                    if len(combined_name) > maxlength:
                        logger.warning(
                            f"Combined name '{combined_name}' exceeds maxlength {maxlength}, using individual fields instead"
                        )
                        return data  # Fall back to individual fields
                except ValueError:
                    logger.warning(f"Invalid maxlength attribute '{maxlength_attr}' for full_name field")

            # Create new data dict with full_name prioritized
            modified_data = data.copy()
            if combined_name:
                modified_data["full_name"] = combined_name
                # Remove individual name fields to avoid conflicts
                _ = modified_data.pop("first_name", None)
                _ = modified_data.pop("last_name", None)
                logger.info(f"Detected full name field, combining names: '{combined_name}'")

            return modified_data

        # If no full_name field exists, keep individual fields as is
        return data

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
                    # Get the first element and check its tag name
                    tag_name = await locator.first.evaluate("el => el.tagName.toLowerCase()")

                    # For select elements, verify they have options
                    if tag_name == "select":
                        options = locator.first.locator("option")
                        if await options.count() > 0:
                            self._found_fields[field_type] = locator.first
                            return self._found_fields[field_type]
                    # For input elements, just verify it's an input
                    elif tag_name == "input":
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
                                    # Verify it's a valid input/select element
                                    tag_name = await field.first.evaluate("el => el.tagName.toLowerCase()")
                                    if tag_name in ["input", "select"]:
                                        self._found_fields[field_type] = field.first
                                        return self._found_fields[field_type]

                                # Try by exact attribute match
                                field = self.page.locator(f'{element_type}[id="{for_attr}"]')
                                if await field.count() > 0:
                                    # Verify it's a valid input/select element
                                    tag_name = await field.first.evaluate("el => el.tagName.toLowerCase()")
                                    if tag_name in ["input", "select"]:
                                        self._found_fields[field_type] = field.first
                                        return self._found_fields[field_type]

                                # Try by name attribute
                                field = self.page.locator(f'{element_type}[name="{for_attr}"]')
                                if await field.count() > 0:
                                    # Verify it's a valid input/select element
                                    tag_name = await field.first.evaluate("el => el.tagName.toLowerCase()")
                                    if tag_name in ["input", "select"]:
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
                                # Verify it's a valid input/select element
                                tag_name: str = await field.first.evaluate("el => el.tagName.toLowerCase()")
                                if tag_name in ["input", "select"]:
                                    self._found_fields[field_type] = field.first
                                    return self._found_fields[field_type]

                    except Exception as e:
                        logger.error(f"Warning: Failed to find related field for label: {str(e)}")
                        continue

        except Exception as e:
            logger.error(f"Warning: Error while searching by label: {str(e)}")

        return None

    async def fill_form(self, data: dict[str, str]) -> dict[str, Locator | str]:
        """
        Fill form fields with the provided data.

        Args:
            data: Dictionary containing form data with keys matching FIELD_SELECTORS

        Returns:
            Dictionary mapping field types to either Locator (success) or failure type string
        """
        # Detect and resolve name field conflicts before filling
        data = await self._detect_name_field_conflicts(data)

        result: dict[str, Locator | str] = {}
        filled_count = 0
        failed_fields: list[str] = []
        not_found_fields: list[str] = []

        # Randomize the order of fields to make form filling more human-like
        field_types = list(data.keys())

        for field_type in field_types:
            value = data[field_type]
            if not value:  # Skip empty values
                result[field_type] = "empty_value"
                continue

            field = await self.find_field(field_type)
            if not field:
                not_found_fields.append(field_type)
                logger.debug(f"Field {field_type} not found on page")
                result[field_type] = "not_found"
                continue

            try:
                # Handle select elements
                tag_name: str = await field.evaluate("el => el.tagName.toLowerCase()")
                if tag_name == "select":
                    success = await self._fill_select_field(field, field_type, value)
                    if success:
                        filled_count += 1
                        result[field_type] = field
                    else:
                        failed_fields.append(field_type)
                        result[field_type] = "select_option_not_found"
                # Handle input elements
                else:
                    success = await self._fill_input_field(field, field_type, value)
                    if success:
                        filled_count += 1
                        result[field_type] = field
                    else:
                        failed_fields.append(field_type)
                        result[field_type] = "input_fill_failed"

            except Exception as e:
                logger.warning(f"Failed to fill {field_type} field: {str(e)}")
                failed_fields.append(field_type)
                result[field_type] = "exception_occurred"

        # Log summary with better details
        total_attempted = len([v for v in data.values() if v])  # Count non-empty values
        logger.info(
            f"Form filling completed: {filled_count}/{total_attempted} fields filled successfully. "
            + f"Failed: {len(failed_fields)}, Not found: {len(not_found_fields)}"
        )

        if failed_fields:
            logger.info(f"Failed fields: {', '.join(failed_fields)}")
        if not_found_fields:
            logger.info(f"Not found fields: {', '.join(not_found_fields)}")

        # hacky: scroll to the first filled element if any fields were successfully filled
        filled_locators = [locator for locator in result.values() if isinstance(locator, PlaywrightLocator)]
        if filled_locators:
            try:
                _ = await filled_locators[0].scroll_into_view_if_needed()  # pyright: ignore [reportAttributeAccessIssue, reportUnknownMemberType, reportUnknownVariableType]
                logger.debug("Scrolled to first filled form element")
            except Exception as e:
                logger.warning(f"Failed to scroll to first filled element: {str(e)}")

        return result

    async def _fill_select_field(self, field: Locator, field_type: str, value: str) -> bool:
        """Fill a select field with the given value."""
        try:
            # Try exact match first
            _ = await field.select_option(value=value)
            logger.debug(f"Successfully filled {field_type} field (exact match)")
            await asyncio.sleep(random.uniform(0.1, 0.5))
            return True
        except Exception:
            try:
                # If exact match fails, try case-insensitive match
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
                        await asyncio.sleep(random.uniform(0.1, 0.5))
                        return True

                logger.warning(f"Failed to fill {field_type} field: No matching option found for '{value}'")
                return False
            except Exception as e:
                logger.warning(f"Failed to fill {field_type} field (case-insensitive match): {str(e)}")
                return False

    async def _fill_input_field(self, field: Locator, field_type: str, value: str) -> bool:
        """Fill an input field with the given value."""
        try:
            await field.hover()
            await asyncio.sleep(random.uniform(0.1, 0.3))

            # Check for maxlength constraint
            maxlength_attr = await field.get_attribute("maxlength")
            if maxlength_attr:
                try:
                    maxlength = int(maxlength_attr)
                    if len(value) > maxlength:
                        logger.warning(f"Value for {field_type} exceeds maxlength {maxlength}, truncating")
                        value = value[:maxlength]
                except ValueError:
                    logger.warning(f"Invalid maxlength attribute '{maxlength_attr}' for {field_type}")

            current_value = await field.input_value()
            if current_value != "":
                await field.clear()

            await asyncio.sleep(random.uniform(0.1, 0.3))
            await field.press_sequentially(value, delay=random.uniform(50, 150))

            # hacky way to ignore address popups for now
            if field_type == "address1":
                await asyncio.sleep(random.uniform(3, 3.5))

                logger.info("waited, now escaping")
                await self.page.keyboard.press("Escape")
                # TODO: detect autocomplete elements instead
                # <div class="pac-container pac-logo hdpi" style="width: 436px; position: absolute; left: 15px; top: 305px; display: none;"></div>
                # <h3 id="shipping-address1-autocomplete-title" class="_1tnwc9fi _1tnwc9fh _1fragemp2 _1fragemsw">

            logger.debug(f"Successfully filled {field_type} field")
            await asyncio.sleep(random.uniform(0.1, 0.5))
            return True
        except Exception as e:
            logger.warning(f"Failed to fill {field_type} field: {str(e)}")
            return False

    async def get_found_fields(self) -> dict[str, bool]:
        """
        Return a dictionary indicating which fields were found on the page.

        Returns:
            Dict mapping field types to boolean indicating if they were found.
        """
        return {field_type: bool(await self.find_field(field_type)) for field_type in self.FIELD_SELECTORS.keys()}
