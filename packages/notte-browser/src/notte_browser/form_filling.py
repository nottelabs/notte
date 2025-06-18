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


class FormTypes:
    LOGIN: str = "login"
    REGISTRATION: str = "registration"
    IDENTITY: str = "identity"
    CREDIT_CARD: str = "credit_card"
    PASSWORD_CHANGE: str = "password_change"


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

    # Keywords that indicate a registration form
    REGISTRATION_KEYWORDS: set[str] = {
        "register",
        "create account",
        "new account",
        "create password",
    }

    # Keywords that indicate a password change form
    PASSWORD_CHANGE_KEYWORDS: set[str] = {"change password", "update password", "new password", "reset password"}

    def __init__(self, page: Page):
        """Initialize the FormFiller with a Playwright page."""
        self.page: Page = page
        self._found_fields: dict[str, Locator] = {}
        self._form_type: str | None = None

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
                print(f"Warning: Invalid selector {selector}: {str(e)}")
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
                            print(f"Warning: Failed to find field for label with for={for_attr}: {str(e)}")
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
                        print(f"Warning: Failed to find related field for label: {str(e)}")
                        continue

        except Exception as e:
            print(f"Warning: Error while searching by label: {str(e)}")

        return None

    async def _get_form_type(self) -> str:
        """Determine the type of form on the page."""
        if self._form_type:
            return self._form_type

        try:
            # Check for credit card fields
            cc_number = await self.find_field("cc_number")
            cc_cvv = await self.find_field("cc_cvv")
            cc_exp = await self.find_field("cc_exp")

            if cc_number and (cc_cvv or cc_exp):
                self._form_type = FormTypes.CREDIT_CARD
                return self._form_type

            # Check for password change form
            current_password = await self.find_field("current_password")
            new_password = await self.find_field("new_password")

            if current_password and new_password:
                self._form_type = FormTypes.PASSWORD_CHANGE
                return self._form_type

            # Check page text for registration indicators
            try:
                page_text = await self.page.text_content("body") or ""
                page_text = page_text.lower()

                if any(keyword in page_text for keyword in self.REGISTRATION_KEYWORDS):
                    import logging

                    logging.warning(f"{[keyword for keyword in self.REGISTRATION_KEYWORDS if keyword in page_text]}")
                    self._form_type = FormTypes.REGISTRATION
                    return self._form_type
            except Exception as e:
                print(f"Warning: Error while checking page text: {str(e)}")

            # Check for login form
            username = await self.find_field("username")
            if username and current_password and not new_password:
                self._form_type = FormTypes.LOGIN
                return self._form_type

            # Default to identity if we find common identity fields
            first_name = await self.find_field("first_name")
            email = await self.find_field("email")
            address1 = await self.find_field("address1")

            if first_name or email or address1:
                self._form_type = FormTypes.IDENTITY
                return self._form_type

        except Exception as e:
            print(f"Warning: Error while determining form type: {str(e)}")
            return FormTypes.IDENTITY  # Default on error

        return FormTypes.IDENTITY  # Default

    async def fill_form(self, data: dict[str, str]) -> None:
        """
        Fill a form with the provided data based on the detected form type.

        Args:
            data: Dictionary containing form data with keys matching FIELD_SELECTORS
        """
        form_type = await self._get_form_type()
        import logging

        logging.warning(f"{form_type=}")

        # Fill fields based on form type
        if form_type == FormTypes.CREDIT_CARD:
            await self._fill_credit_card_form(data)
        elif form_type in [FormTypes.LOGIN, FormTypes.REGISTRATION]:
            await self._fill_login_form(data)
        elif form_type == FormTypes.PASSWORD_CHANGE:
            await self._fill_password_change_form(data)
        else:  # IDENTITY
            await self._fill_identity_form(data)

    async def _fill_identity_form(self, identity_data: dict[str, str]) -> None:
        """Fill identity-specific fields."""
        identity_fields = [
            "title",
            "first_name",
            "middle_name",
            "last_name",
            "email",
            "company",
            "address1",
            "address2",
            "address3",
            "city",
            "state",
            "postal_code",
            "country",
            "phone",
        ]
        await self._fill_fields(identity_fields, identity_data)

    async def _fill_credit_card_form(self, card_data: dict[str, str]) -> None:
        """Fill credit card-specific fields."""
        card_fields = ["cc_name", "cc_number", "cc_exp_month", "cc_exp_year", "cc_exp", "cc_cvv"]
        await self._fill_fields(card_fields, card_data)

        # Handle combined expiration date if needed
        if "cc_exp" in card_data and not (
            await self.find_field("cc_exp_month") or await self.find_field("cc_exp_year")
        ):
            exp_field = await self.find_field("cc_exp")
            if exp_field:
                await exp_field.fill(card_data["cc_exp"])

    async def _fill_login_form(self, login_data: dict[str, str]) -> None:
        """Fill login-specific fields."""
        login_fields = ["username", "current_password", "new_password", "totp"]
        await self._fill_fields(login_fields, login_data)

    async def _fill_password_change_form(self, password_data: dict[str, str]) -> None:
        """Fill password change-specific fields."""
        password_fields = ["current_password", "new_password"]
        await self._fill_fields(password_fields, password_data)

    async def _fill_fields(self, field_types: list[str], data: dict[str, str]) -> None:
        """Helper method to fill multiple fields."""
        for field_type in field_types:
            if field_type not in data or not data[field_type]:
                continue

            field = await self.find_field(field_type)
            import logging

            logging.warning(f"{field_type=} {field=}")
            if field:
                tag_name: str = await field.evaluate("el => el.tagName.toLowerCase()")
                try:
                    # Check if it's a select element
                    if tag_name == "select":
                        # Try exact match first
                        _ = await field.select_option(value=data[field_type])
                    else:
                        await field.fill(data[field_type])
                    print(f"Filled {field_type} field with value")
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
                            target_value: str = data[field_type].lower()
                            for option in options:
                                lower_value: str = option["value"].lower()
                                lower_text: str = option["text"].lower()
                                if lower_value == target_value or lower_text == target_value:
                                    _ = field.select_option(value=option["value"])
                                    print(f"Filled {field_type} field with value (case-insensitive match)")
                                    break
                            else:
                                print(f"Failed to fill {field_type} field: No matching option found")
                        else:
                            print(f"Failed to fill {field_type} field: {str(e)}")
                    except Exception as e2:
                        print(f"Failed to fill {field_type} field (both attempts): {str(e2)}")

    async def get_found_fields(self) -> dict[str, bool]:
        """
        Return a dictionary indicating which fields were found on the page.

        Returns:
            Dict mapping field types to boolean indicating if they were found.
        """
        return {field_type: bool(await self.find_field(field_type)) for field_type in self.FIELD_SELECTORS.keys()}
