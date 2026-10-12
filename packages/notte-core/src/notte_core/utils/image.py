import io
from base64 import b64encode
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import aiohttp
import requests
from PIL import Image


def image_from_bytes(image_bytes: bytes) -> Image.Image | None:
    try:
        image = Image.open(io.BytesIO(image_bytes))
    except Image.UnidentifiedImageError:
        return None
    return image


def construct_image_url(base_page_url: str, image_src: str) -> str:
    """
    Constructs absolute URL for image source, handling relative and absolute paths.

    Args:
        base_page_url: The URL of the page containing the image
        image_src: The src attribute value from the img tag

    Returns:
        str: Absolute URL for the image
    """
    # If image_src is already absolute URL, return as is
    if image_src.startswith(("http://", "https://", "//")):
        return image_src.replace("//", "https://", 1) if image_src.startswith("//") else image_src

    # For relative paths, use urljoin which handles path resolution
    return urljoin(base_page_url, image_src)


def img_down(link: str, output_dir: str | None = None) -> Path | None:
    """
    Downloads and saves an image from a URL, handling different formats.

    Args:
        link: URL of the image to download
        output_dir: Optional directory to save images (defaults to current directory)
    """
    try:
        # Get file extension from URL
        parsed_url = urlparse(link)
        extension = Path(parsed_url.path).suffix.lower()

        # Generate output filename
        filename = Path(parsed_url.path).name
        if not extension:
            filename += ".jpg"  # Default extension

        # Setup output directory
        output_path = Path(output_dir) if output_dir else Path.cwd()
        output_path.mkdir(parents=True, exist_ok=True)

        # Handle SVG files differently
        if extension == ".svg":
            response = requests.get(link)
            if response.status_code == 200:
                _ = (output_path / filename).write_bytes(response.content)
                print(f"Successfully saved SVG: {filename}")
                return output_path / filename

        # For other image formats
        response = requests.get(link)
        if response.status_code == 200:
            image_file = io.BytesIO(response.content)
            try:
                image = Image.open(image_file)
                output_path = Path(output_dir) if output_dir else Path.cwd()
                output_path.mkdir(parents=True, exist_ok=True)
                image_output_path = output_path / filename
                image.save(image_output_path)
                print(f"Successfully saved: {filename}")
                return image_output_path
            except Exception as e:
                print(f"Error processing image {filename}: {str(e)}")
                return None
        else:
            print(f"Failed to download {link}: HTTP {response.status_code}")
            return None
    except Exception as e:
        print(f"Error downloading {link}: {str(e)}")
        return None


def get_images_as_files(image_urls: list[str]) -> list[Path | None]:
    # Usage:
    return [img_down(image, output_dir="downloaded_images") for image in image_urls]


async def get_images_as_base64(images_urls: list[str]) -> dict[str, Any]:
    """Returns images as base64 strings with metadata"""
    img_lst: list[dict[str, Any]] = []

    async with aiohttp.ClientSession() as session:
        for url in images_urls:
            try:
                async with session.get(url) as response:
                    if response.status == 200:
                        content = await response.read()
                        img_lst.append(
                            {
                                "url": url,
                                "content_type": response.headers.get("content-type"),
                                "size": len(content),
                                "data": b64encode(content).decode("utf-8"),
                            }
                        )
            except Exception as e:
                print(f"Error downloading {url}: {str(e)}")

    return {"total_images": len(img_lst), "images": img_lst}
