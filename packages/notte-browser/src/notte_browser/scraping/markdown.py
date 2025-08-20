import markdownify  # type: ignore[import]
from main_content_extractor import MainContentExtractor  # type: ignore[import]
from notte_core.browser.snapshot import BrowserSnapshot

from notte_browser.window import BrowserWindow


class MainContentScrapingPipe:
    """
    Data scraping pipe that scrapes data from the page
    """

    @staticmethod
    def forward(
        content: str,
        scrape_links: bool,
        output_format: str = "markdown",
    ) -> str:
        return MainContentExtractor.extract(  # type: ignore[attr-defined]
            html=content,
            output_format=output_format,
            include_links=scrape_links,
        )


class VisibleMarkdownConverter(MarkdownConverter):
    """Ignore hidden content on the page and include form values and aria-labels"""

    def convert_soup(self, soup: BeautifulSoup):  # pyright: ignore [reportImplicitOverride, reportUnknownParameterType]
        # Remove hidden elements before conversion
        for element in soup.find_all(style=True):
            if not hasattr(element, "attrs") or element.attrs is None:  # pyright: ignore [reportAttributeAccessIssue, reportUnknownMemberType]
                continue

            style = element.get("style", "")  # pyright: ignore [reportUnknownVariableType, reportUnknownMemberType, reportAttributeAccessIssue]
            if "display:none" in style.replace(" ", "") or "visibility:hidden" in style.replace(" ", ""):  # pyright: ignore [reportUnknownMemberType, reportOptionalMemberAccess, reportAttributeAccessIssue]
                element.decompose()

        return super().convert_soup(soup)  # pyright: ignore [reportUnknownVariableType, reportUnknownMemberType]

    def convert_input(self, el, text, convert_as_inline):  # pyright: ignore [reportImplicitOverride]
        """Convert input elements, including their values and aria-labels"""
        input_type = el.get("type", "text")
        value = el.get("value", "")
        aria_label = el.get("aria-label", "")
        name = el.get("name", "")
        placeholder = el.get("placeholder", "")
        checked = el.get("checked")

        # Build the markdown representation
        parts = []

        # Add label/name information
        if aria_label:
            parts.append(f"**{aria_label}**")
        elif name:
            parts.append(f"**{name}**")
        elif placeholder:
            parts.append(f"**{placeholder}**")
        else:
            parts.append(f"**{input_type} input**")

        # Add type-specific information
        if input_type in ["checkbox", "radio"]:
            if checked is not None:
                status = "☑" if checked else "☐"
                parts.append(f"{status} {value if value else input_type}")
            else:
                parts.append(f"☐ {value if value else input_type}")
        elif input_type == "file":
            parts.append("📁 File upload")
            if value:
                parts.append(f"Selected: `{value}`")
        elif input_type in ["submit", "button"]:
            button_text = value or text or "Button"
            parts.append(f"[{button_text}]")
        else:
            # Text, email, password, number, etc.
            if value:
                parts.append(f"Value: `{value}`")
            elif placeholder:
                parts.append(f"Placeholder: `{placeholder}`")

        return " - ".join(parts) + "\n\n"

    def convert_textarea(self, el, text, convert_as_inline):  # pyright: ignore [reportImplicitOverride]
        """Convert textarea elements, including their values and aria-labels"""
        aria_label = el.get("aria-label", "")
        name = el.get("name", "")
        placeholder = el.get("placeholder", "")
        value = el.get_text() or el.get("value", "")

        # Build the markdown representation
        parts = []

        # Add label information
        if aria_label:
            parts.append(f"**{aria_label}**")
        elif name:
            parts.append(f"**{name}**")
        elif placeholder:
            parts.append(f"**{placeholder}**")
        else:
            parts.append("**Textarea**")

        # Add content
        if value.strip():
            # For multiline text, use code block
            if "\n" in value:
                return " - ".join(parts) + f"\n```\n{value}\n```\n\n"
            else:
                parts.append(f"Value: `{value}`")
        elif placeholder:
            parts.append(f"Placeholder: `{placeholder}`")

        return " - ".join(parts) + "\n\n"

    def convert_select(self, el, text, convert_as_inline):  # pyright: ignore [reportImplicitOverride]
        """Convert select elements, including selected options and aria-labels"""
        aria_label = el.get("aria-label", "")
        name = el.get("name", "")
        multiple = el.get("multiple") is not None

        # Build the markdown representation
        parts = []

        # Add label information
        if aria_label:
            parts.append(f"**{aria_label}**")
        elif name:
            parts.append(f"**{name}**")
        else:
            parts.append("**Select**")

        if multiple:
            parts.append("(Multiple selection)")

        # Get options
        options = el.find_all("option")
        selected_options = []
        all_options = []

        for option in options:
            option_value = option.get("value", "")
            option_text = option.get_text().strip()
            display_text = option_text or option_value

            if option.get("selected") is not None:
                selected_options.append(display_text)

            if display_text:
                all_options.append(display_text)

        # Add selected options
        if selected_options:
            if len(selected_options) == 1:
                parts.append(f"Selected: `{selected_options[0]}`")
            else:
                parts.append(f"Selected: `{', '.join(selected_options)}`")

        # Add available options (limited to avoid cluttering)
        if all_options and len(all_options) <= 10:
            parts.append(f"Options: {', '.join(all_options)}")
        elif all_options:
            parts.append(f"Options: {', '.join(all_options[:8])}... (+{len(all_options) - 8} more)")

        return " - ".join(parts) + "\n\n"

    def convert_button(self, el, text, convert_as_inline):  # pyright: ignore [reportImplicitOverride]
        """Convert button elements, including their text and aria-labels"""
        aria_label = el.get("aria-label", "")
        button_type = el.get("type", "button")
        value = el.get("value", "")

        # Get button text
        button_text = text.strip() or value or aria_label

        if not button_text:
            button_text = f"{button_type} button"

        return f"[{button_text}]\n\n"


class MarkdownifyScrapingPipe:
    """
    Data scraping pipe that scrapes data from the page
    """

    @staticmethod
    async def forward(
        window: BrowserWindow,
        snapshot: BrowserSnapshot,
        only_main_content: bool,
        scrape_links: bool,
        scrape_images: bool,
        include_iframes: bool = True,
    ) -> str:
        if params.only_main_content:
            html = MainContentScrapingPipe.forward(
                (await window.content()), scrape_links=params.scrape_links, output_format="html"
            )
        else:
            # Get HTML content with form values enhanced
            html = await window.content()
        print(html)

        content: str = markdownify.markdownify(html, strip=strip)  # type: ignore[attr-defined]

        # manually append iframe text into the content so it's readable by the LLM (includes cross-origin iframes)
        if include_iframes:
            for iframe in window.page.frames:
                if iframe.url != window.page.url and not iframe.url.startswith("data:"):
                    content += f"\n\nIFRAME {iframe.url}:\n"  # type: ignore[attr-defined]
                    content += markdownify.markdownify(await iframe.content())  # type: ignore[attr-defined]

        return content  # type: ignore[return-value]
