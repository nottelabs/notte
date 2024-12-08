from bs4 import BeautifulSoup


def clean_html_for_llm(html_content: str) -> str:
    # Parse the HTML
    soup = BeautifulSoup(html_content, "html.parser")

    for tag in soup(["style", "script", "head"]):
        tag.decompose()

    # Remove class attributes from all tags
    for tag in soup.find_all(True):  # True finds all tags
        for attr in ["class", "style", "target", "data-special-purpose-id", "tabindex"]:
            if attr in tag.attrs:
                del tag.attrs[attr]

    # Remove empty tags
    for tag in soup.find_all():
        if not tag.get_text(strip=True):  # Checks if the tag is empty
            tag.decompose()

    # Get the cleaned text
    # cleaned_text = soup.get_text(separator=" ", strip=True)
    # Get the cleaned HTML
    cleaned_html = str(soup)
    return cleaned_html
