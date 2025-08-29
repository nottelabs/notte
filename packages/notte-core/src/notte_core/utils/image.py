import io
import os
import textwrap
from base64 import b64encode
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import aiohttp
import requests
from PIL import Image, ImageDraw, ImageFont


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


def get_emoji_capable_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """
    Load the bundled OpenSansEmoji font that supports emojis, falling back to default if not available.

    Args:
        size: Font size in pixels

    Returns:
        PIL font object that supports emojis if available, otherwise default font
    """
    # Get the path to the bundled font file
    current_dir = os.path.dirname(os.path.abspath(__file__))
    font_path = os.path.join(current_dir, "OpenSansEmoji.otf")

    # Try to load the bundled emoji font
    if os.path.exists(font_path):
        try:
            return ImageFont.truetype(font_path, size)
        except (OSError, IOError):
            pass

    # Fall back to default font if bundled font not found or fails to load
    return ImageFont.load_default(size)


def draw_text_with_rounded_background(
    img: Image.Image,
    text: str,
    position: tuple[int, int],
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont | None = None,
    text_color: str = "white",
    bg_color: tuple[int, int, int, int] = (0, 0, 0, 166),
    padding: int = 10,
    corner_radius: int = 12,
    anchor: str = "mm",
    max_width: int = 30,
    font_size: int | None = None,
) -> None:
    """
    Draw text with a semi-transparent rounded rectangle background.

    Args:
        img: PIL Image to draw on
        text: Text to display
        position: (x, y) position for the text
        font: Font to use for the text (if None, will try to use emoji-capable font)
        text_color: Color of the text (default: white)
        bg_color: Background color as RGBA tuple (default: black with 65% opacity)
        padding: Padding around the text in pixels (default: 10)
        corner_radius: Radius of the rounded corners (default: 12)
        anchor: Text anchor position (default: "mm" for middle-middle)
        max_width: Maximum characters per line for text wrapping (default: 30)
        font_size: Font size in pixels (used if font is None)
    """
    draw = ImageDraw.Draw(img)

    # Use emoji-capable font if no font provided
    if font is None:
        if font_size is None:
            # Estimate font size based on image dimensions
            font_size = max(min(img.size) // 25, 12)
        font = get_emoji_capable_font(font_size)

    # Prepare the text with wrapping
    wrapped_text = "\n".join(textwrap.wrap(text, width=max_width))

    # Calculate text bounding box
    bbox = draw.textbbox(position, wrapped_text, anchor=anchor, font=font)

    # Add padding around the text
    bg_bbox = (bbox[0] - padding, bbox[1] - padding, bbox[2] + padding, bbox[3] + padding)

    # Create rounded rectangle using a mask approach
    x1, y1, x2, y2 = bg_bbox
    width = int(x2 - x1)
    height = int(y2 - y1)

    # Create a mask for the rounded rectangle
    mask = Image.new("L", (width, height), 0)
    mask_draw = ImageDraw.Draw(mask)

    # Draw the rounded rectangle mask
    mask_draw.rounded_rectangle([0, 0, width, height], radius=corner_radius, fill=255)

    # Create the background with proper alpha
    bg_rect = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    bg_draw = ImageDraw.Draw(bg_rect)
    bg_draw.rounded_rectangle([0, 0, width, height], radius=corner_radius, fill=bg_color)

    # Create a background layer for the entire image
    bg_layer = Image.new("RGBA", img.size, (0, 0, 0, 0))

    # Paste the rounded rectangle onto the background layer using the mask
    bg_layer.paste(bg_rect, (int(x1), int(y1)), mask)

    # Composite the background onto the image
    img_rgba = img.convert("RGBA")
    img_rgba = Image.alpha_composite(img_rgba, bg_layer)

    # Create a new draw object for the composited image
    draw = ImageDraw.Draw(img_rgba)

    # Draw the text
    draw.text(
        position,
        wrapped_text,
        fill=text_color,
        anchor=anchor,
        font=font,
    )

    # Convert back to RGB if the original image was RGB
    if img.mode == "RGB":
        rgb_img = Image.new("RGB", img_rgba.size, (255, 255, 255))
        rgb_img.paste(img_rgba, mask=img_rgba.split()[-1])
        img.paste(rgb_img)
    else:
        img.paste(img_rgba)
