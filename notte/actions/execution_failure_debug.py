from dataclasses import dataclass
from urllib.parse import urlparse

from patchright.async_api import Frame, Locator, Page


@dataclass
class ElementHtml:
    outer_html: str
    inner_html: str
    text_content: str


@dataclass
class ElementPosition:
    x: float
    y: float
    width: float
    height: float


@dataclass
class ElementAttributes:
    """Stores common element attributes."""

    role: str | None
    tag_name: str | None
    aria_label: str | None
    type: str | None
    name: str | None
    value: str | None
    placeholder: str | None
    href: str | None
    src: str | None
    alt: str | None
    title: str | None
    id: str | None
    class_name: str | None

    @classmethod
    async def create(cls, locator: Locator) -> "ElementAttributes":
        """Creates ElementAttributes by evaluating the element."""
        attrs = await locator.evaluate(
            """element => {
            return {
                role: element.getAttribute('role'),
                tagName: element.tagName.toLowerCase(),
                ariaLabel: element.getAttribute('aria-label'),
                type: element.getAttribute('type'),
                name: element.getAttribute('name'),
                value: element.value,
                placeholder: element.getAttribute('placeholder'),
                href: element.getAttribute('href'),
                src: element.getAttribute('src'),
                alt: element.getAttribute('alt'),
                title: element.getAttribute('title'),
                id: element.id,
                className: element.className
            }
        }"""
        )

        return cls(
            role=attrs["role"],
            tag_name=attrs["tagName"],
            aria_label=attrs["ariaLabel"],
            type=attrs["type"],
            name=attrs["name"],
            value=attrs["value"],
            placeholder=attrs["placeholder"],
            href=attrs["href"],
            src=attrs["src"],
            alt=attrs["alt"],
            title=attrs["title"],
            id=attrs["id"],
            class_name=attrs["className"],
        )


@dataclass
class ComputedStyles:
    display: str
    visibility: str
    opacity: str
    pointer_events: str
    cursor: str
    position: str
    z_index: str


@dataclass
class OverlappingElement:
    tag: str
    id: str
    class_name: str
    z_index: str


@dataclass
class FrameInfo:
    name: str
    url: str
    parent_frame: str | None
    is_detached: bool
    has_selector: bool
    selector_count: int | None

    @classmethod
    async def create(cls, frame: Frame, selector: str) -> "FrameInfo":
        """Creates a FrameInfo instance with frame details."""
        try:
            selector_count = await frame.locator(selector).count()
            has_selector = selector_count > 0
        except Exception:
            selector_count = None
            has_selector = False

        return cls(
            name=frame.name or urlparse(frame.url).path,
            url=frame.url,
            parent_frame=frame.parent_frame.name if frame.parent_frame else None,
            is_detached=frame.is_detached(),
            has_selector=has_selector,
            selector_count=selector_count,
        )


@dataclass
class ExecutionFailureDebug:
    selector: str
    attributes: ElementAttributes
    is_visible: bool
    is_enabled: bool
    is_editable: bool
    element_count: int
    position: ElementPosition | None
    overlapping_elements: list[OverlappingElement]
    frames: list[FrameInfo]
    computed_styles: ComputedStyles
    html: ElementHtml | None

    @classmethod
    async def create(cls, selector: str, page: Page) -> "ExecutionFailureDebug":
        """Creates an ExecutionFailureDebug instance by analyzing the element."""
        element = page.locator(selector)

        # Basic properties
        is_visible = await element.is_visible()
        is_enabled = await element.is_enabled()
        is_editable = await element.is_editable()
        element_count = await element.count()

        # Element attributes
        attributes = await ElementAttributes.create(element)

        # HTML content
        html = None
        try:
            html = ElementHtml(
                outer_html=await element.evaluate("element => element.outerHTML"),
                inner_html=await element.inner_html(),
                text_content=await element.text_content() or "",
            )
        except Exception:
            pass

        # Position
        position = None
        if box := await element.bounding_box():
            position = ElementPosition(x=box["x"], y=box["y"], width=box["width"], height=box["height"])

        # Overlapping elements
        overlapping_elements: list[OverlappingElement] = []
        if position:
            elements = await page.evaluate(
                f"""() => {{
                const elements = document.elementsFromPoint({position.x}, {position.y});
                return elements.map(e => ({{
                    tag: e.tagName,
                    id: e.id,
                    className: e.className,
                    zIndex: window.getComputedStyle(e).zIndex
                }}));
            }}"""
            )
            overlapping_elements = [
                OverlappingElement(tag=e["tag"], id=e["id"], class_name=e["className"], z_index=e["zIndex"])
                for e in elements
            ]

        # Frame information
        frames = [await FrameInfo.create(frame, selector) for frame in page.frames]

        # Computed styles
        styles = await element.evaluate(
            """element => {
            const style = window.getComputedStyle(element);
            return {
                display: style.display,
                visibility: style.visibility,
                opacity: style.opacity,
                pointerEvents: style.pointerEvents,
                cursor: style.cursor,
                position: style.position,
                zIndex: style.zIndex
            }
        }"""
        )
        computed_styles = ComputedStyles(
            display=styles["display"],
            visibility=styles["visibility"],
            opacity=styles["opacity"],
            pointer_events=styles["pointerEvents"],
            cursor=styles["cursor"],
            position=styles["position"],
            z_index=styles["zIndex"],
        )

        return cls(
            selector=selector,
            attributes=attributes,
            is_visible=is_visible,
            is_enabled=is_enabled,
            is_editable=is_editable,
            element_count=element_count,
            position=position,
            overlapping_elements=overlapping_elements,
            frames=frames,
            computed_styles=computed_styles,
            html=html,
        )

    def __str__(self) -> str:
        """Returns a human-readable debug report."""
        lines = [
            f"Element Debug Report for selector: {self.selector}",
            "\nElement Information:",
            f"- Tag: {self.attributes.tag_name}",
            f"- Role: {self.attributes.role}",
        ]

        # Add relevant attributes based on element type
        attr_lines = []
        if self.attributes.type:
            attr_lines.append(f"- Type: {self.attributes.type}")
        if self.attributes.name:
            attr_lines.append(f"- Name: {self.attributes.name}")
        if self.attributes.value:
            attr_lines.append(f"- Value: {self.attributes.value}")
        if self.attributes.placeholder:
            attr_lines.append(f"- Placeholder: {self.attributes.placeholder}")
        if self.attributes.href:
            attr_lines.append(f"- Href: {self.attributes.href}")
        if self.attributes.src:
            attr_lines.append(f"- Src: {self.attributes.src}")
        if self.attributes.alt:
            attr_lines.append(f"- Alt: {self.attributes.alt}")
        if self.attributes.aria_label:
            attr_lines.append(f"- Aria Label: {self.attributes.aria_label}")
        if self.attributes.title:
            attr_lines.append(f"- Title: {self.attributes.title}")
        if self.attributes.id:
            attr_lines.append(f"- ID: {self.attributes.id}")
        if self.attributes.class_name:
            attr_lines.append(f"- Classes: {self.attributes.class_name}")

        lines.extend(attr_lines)

        lines.extend(
            [
                "\nElement State:",
                f"- Visibility: {self.is_visible}",
                f"- Enabled: {self.is_enabled}",
                f"- Editable: {self.is_editable}",
                f"- Element count: {self.element_count}",
            ]
        )

        if self.html:
            lines.extend(
                [
                    "\nHTML Content:",
                    f"- Text content: {self.html.text_content}",
                    "- Inner HTML:",
                    f"  {self.html.inner_html}",
                    "- Outer HTML:",
                    f"  {self.html.outer_html}",
                ]
            )

        if self.position:
            lines.extend(
                [
                    "\nPosition:",
                    f"- X: {self.position.x}",
                    f"- Y: {self.position.y}",
                    f"- Width: {self.position.width}",
                    f"- Height: {self.position.height}",
                ]
            )
        else:
            lines.append("\nPosition: No bounding box (might be hidden)")

        lines.extend(
            [
                "\nComputed styles:",
                f"- Display: {self.computed_styles.display}",
                f"- Visibility: {self.computed_styles.visibility}",
                f"- Opacity: {self.computed_styles.opacity}",
                f"- Pointer events: {self.computed_styles.pointer_events}",
                f"- Cursor: {self.computed_styles.cursor}",
                f"- Position: {self.computed_styles.position}",
                f"- Z-index: {self.computed_styles.z_index}",
            ]
        )

        if self.frames:
            lines.append("\nFrames:")
            for frame in self.frames:
                lines.extend(
                    [
                        f"- Name: {frame.name}",
                        f"  URL: {frame.url}",
                        f"  Parent frame: {frame.parent_frame}",
                        f"  Is detached: {frame.is_detached}",
                        f"  Has selector: {frame.has_selector}",
                        f"  Selector count: {frame.selector_count}",
                    ]
                )

        if self.overlapping_elements:
            lines.append("\nOverlapping elements:")
            for elem in self.overlapping_elements:
                lines.append(f"- {elem.tag} (id: {elem.id}, class: {elem.class_name}, z-index: {elem.z_index})")

        return "\n".join(lines)
