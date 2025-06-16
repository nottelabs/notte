import asyncio
import contextlib
import csv
import functools
import inspect
import json
import time
from collections import defaultdict
from typing import Any, Callable, Dict, List, Optional, ParamSpec, TypeVar, cast

# OpenTelemetry imports
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import Status, StatusCode

P = ParamSpec("P")
R = TypeVar("R")


class OTelProfiler:
    """
    OpenTelemetry-based profiler that captures timing data and generates flamegraphs.
    Uses OpenTelemetry spans for instrumentation and exports timing data for visualization.
    """

    def __init__(self, service_name="async-profiler"):
        """
        Initialize the OpenTelemetry profiler.

        Args:
            service_name (str): Name of the service for tracing context
        """
        self.service_name = service_name
        self.memory_exporter = InMemorySpanExporter()
        self.setup_tracer()
        self.start_time = None

    def setup_tracer(self):
        """Set up OpenTelemetry tracer with in-memory span collection."""
        resource = Resource.create({"service.name": self.service_name})

        # Create tracer provider
        trace.set_tracer_provider(TracerProvider(resource=resource))
        tracer_provider = trace.get_tracer_provider()

        # Add memory exporter to collect spans - use immediate export
        span_processor = SimpleSpanProcessor(self.memory_exporter)
        tracer_provider.add_span_processor(span_processor)

        # Get tracer
        self.tracer = trace.get_tracer(__name__)

    @contextlib.asynccontextmanager
    async def profile(self, operation_name: str, attributes: Optional[Dict[str, Any]] = None):
        """
        Context manager for profiling a section of code using OpenTelemetry spans.

        Args:
            operation_name (str): Name of the operation being profiled
            attributes (dict, optional): Additional attributes to attach to the span
        """
        if self.start_time is None:
            self.start_time = time.perf_counter()

        with self.tracer.start_as_current_span(operation_name) as span:
            # Add custom attributes
            if attributes:
                for key, value in attributes.items():
                    span.set_attribute(key, value)

            # Add timing attributes
            span.set_attribute("start_time", time.perf_counter())

            try:
                yield span
            except Exception as e:
                span.set_status(Status(StatusCode.ERROR, str(e)))
                raise
            finally:
                span.set_attribute("end_time", time.perf_counter())

    @contextlib.contextmanager
    def profile_sync(self, operation_name: str, attributes: Optional[Dict[str, Any]] = None):
        """
        Synchronous context manager for profiling a section of code using OpenTelemetry spans.

        Args:
            operation_name (str): Name of the operation being profiled
            attributes (dict, optional): Additional attributes to attach to the span
        """
        if self.start_time is None:
            self.start_time = time.perf_counter()

        with self.tracer.start_as_current_span(operation_name) as span:
            # Add custom attributes
            if attributes:
                for key, value in attributes.items():
                    span.set_attribute(key, value)

            # Add timing attributes
            span.set_attribute("start_time", time.perf_counter())

            try:
                yield span
            except Exception as e:
                span.set_status(Status(StatusCode.ERROR, str(e)))
                raise
            finally:
                span.set_attribute("end_time", time.perf_counter())

    def profiled(
        self, operation_name: Optional[str] = None, attributes: Optional[Dict[str, Any]] = None
    ) -> Callable[[Callable[P, R]], Callable[P, R]]:
        """
        Decorator that profiles a function using OpenTelemetry spans.
        Works with both synchronous and asynchronous functions.

        For class methods, uses the full qualified name (classname.functionname) as the operation name
        unless a custom name is provided.

        Args:
            operation_name (str, optional): Name of the operation. Defaults to the qualified function name.
            attributes (dict, optional): Additional attributes to attach to the span.

        Returns:
            Callable: Wrapped function with profiling
        """
        # Handle case where decorator is used without parentheses
        if callable(operation_name):
            func = operation_name
            return self.profiled()(func)

        def decorator(func: Callable[P, R]) -> Callable[P, R]:
            # Use provided operation name or fall back to qualified name
            if operation_name is not None:
                op_name = operation_name
            else:
                # Get qualified name for class methods, otherwise use function name
                op_name = func.__qualname__ if "." in func.__qualname__ else func.__name__

            # Handle async functions
            if inspect.iscoroutinefunction(func):

                @functools.wraps(func)
                async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
                    async with self.profile(op_name, attributes):
                        return await func(*args, **kwargs)

                return cast(Callable[P, R], async_wrapper)

            # Handle sync functions
            else:

                @functools.wraps(func)
                def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
                    with self.profile_sync(op_name, attributes):
                        return func(*args, **kwargs)

                return cast(Callable[P, R], sync_wrapper)

        return decorator

    def get_span_data(self) -> List[Dict[str, Any]]:
        """Extract timing data from collected spans."""
        spans = self.memory_exporter.get_finished_spans()
        span_data = []

        for span in spans:
            # Extract timing info
            start_time = span.start_time / 1_000_000_000  # Convert from nanoseconds
            end_time = span.end_time / 1_000_000_000
            duration = end_time - start_time

            # Get span IDs from context
            span_id = format(span.context.span_id, "016x")

            # Get parent span ID if available
            parent_span_id = None
            if span.parent and hasattr(span.parent, "span_id"):
                parent_span_id = format(span.parent.span_id, "016x")
            elif hasattr(span, "parent") and span.parent:
                # Try to get from span context
                try:
                    parent_span_id = format(span.parent.span_id, "016x")
                except:
                    parent_span_id = None

            span_info = {
                "name": span.name,
                "span_id": span_id,
                "parent_span_id": parent_span_id,
                "start_time": start_time - (self.start_time or start_time),
                "end_time": end_time - (self.start_time or start_time),
                "duration": duration,
                "attributes": dict(span.attributes) if span.attributes else {},
                "status": span.status.status_code.name if span.status else "OK",
            }
            span_data.append(span_info)

        return sorted(span_data, key=lambda x: x["start_time"])

    def build_span_hierarchy(self, span_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Build hierarchical structure from flat span data."""
        # Since OpenTelemetry's parent tracking can be complex with async,
        # we'll build hierarchy based on timing overlap and naming patterns

        # Sort by start time
        sorted_spans = sorted(span_data, key=lambda x: x["start_time"])

        # Build a simple hierarchy based on timing containment
        for i, span in enumerate(sorted_spans):
            span["children"] = []
            span["depth"] = 0

            # Find potential parent (latest starting span that contains this one)
            for j in range(i - 1, -1, -1):
                potential_parent = sorted_spans[j]

                # Check if this span is contained within the potential parent
                if (
                    potential_parent["start_time"] <= span["start_time"]
                    and potential_parent["end_time"] >= span["end_time"]
                ):
                    potential_parent["children"].append(span)
                    span["depth"] = potential_parent["depth"] + 1
                    break

        # Return only root spans (depth 0)
        return [span for span in sorted_spans if span["depth"] == 0]

    def generate_stack_paths(self, span_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Generate stack paths for flamegraph from span hierarchy."""
        hierarchy = self.build_span_hierarchy(span_data)
        flamegraph_data = []

        def traverse_spans(spans, path_stack=[]):
            for span in spans:
                current_path = path_stack + [span["name"]]
                stack_path = ";".join(current_path)

                flamegraph_data.append(
                    {
                        "stack_path": stack_path,
                        "duration": span["duration"],
                        "start_time": span["start_time"],
                        "end_time": span["end_time"],
                        "depth": len(current_path) - 1,
                        "name": span["name"],
                    }
                )

                # Traverse children
                if span["children"]:
                    traverse_spans(span["children"], current_path)

        traverse_spans(hierarchy)
        return flamegraph_data

    def save_results(self, output_file="otel_profile_results.csv"):
        """Save profiling results to CSV."""
        span_data = self.get_span_data()
        flamegraph_data = self.generate_stack_paths(span_data)

        try:
            with open(output_file, "w", newline="") as csvfile:
                fieldnames = ["name", "stack_path", "start_time", "end_time", "duration", "depth"]
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(flamegraph_data)
            print(f"Profiling results saved to {output_file}")
        except Exception as e:
            print(f"Error saving results: {e}")

    def print_results(self):
        """Print hierarchical profiling results."""
        span_data = self.get_span_data()
        flamegraph_data = self.generate_stack_paths(span_data)

        print("OpenTelemetry Profiling Results:")
        print("-" * 80)
        print(f"{'Operation':<40} {'Start':<10} {'End':<10} {'Duration':<12}")
        print("-" * 80)

        for item in flamegraph_data:
            indent = "  " * item["depth"]
            name = f"{indent}{item['name']}"
            print(f"{name:<40} {item['start_time']:<10.6f} {item['end_time']:<10.6f} {item['duration']:<12.6f}")

    def generate_flamegraph_svg(self, output_file="flamegraph.svg", width=1200, height=600):
        """Generate a properly scaled SVG flamegraph with interactive timeline controls."""
        span_data = self.get_span_data()
        flamegraph_data = self.generate_stack_paths(span_data)

        if not flamegraph_data:
            print("No data to generate flamegraph")
            return

        # Find the overall time bounds
        min_start = min(item["start_time"] for item in flamegraph_data)
        max_end = max(item["end_time"] for item in flamegraph_data)
        total_time = max_end - min_start

        if total_time <= 0:
            print("No meaningful timing data for flamegraph")
            return

        print(f"Flamegraph time range: {min_start:.6f}s to {max_end:.6f}s (total: {total_time:.6f}s)")

        # Group by depth and handle overlapping spans
        layers = defaultdict(list)
        max_depth = 0

        # First pass: group by depth
        for item in flamegraph_data:
            layers[item["depth"]].append(item)
            max_depth = max(max_depth, item["depth"])

        # Second pass: handle overlapping spans by adjusting vertical position
        adjusted_layers = defaultdict(list)
        for depth, items in layers.items():
            # Sort items by start time
            sorted_items = sorted(items, key=lambda x: x["start_time"])

            # Track occupied time ranges at each sublayer
            sublayers = []  # List of lists of (start, end) tuples

            for item in sorted_items:
                # Find a sublayer where this item doesn't overlap
                placed = False
                for sublayer_idx, sublayer in enumerate(sublayers):
                    # Check if item overlaps with any span in this sublayer
                    overlaps = False
                    for start, end in sublayer:
                        if not (item["end_time"] <= start or item["start_time"] >= end):
                            overlaps = True
                            break

                    if not overlaps:
                        # Place item in this sublayer
                        sublayer.append((item["start_time"], item["end_time"]))
                        item["sublayer"] = sublayer_idx
                        adjusted_layers[depth].append(item)
                        placed = True
                        break

                if not placed:
                    # Create new sublayer
                    sublayers.append([(item["start_time"], item["end_time"])])
                    item["sublayer"] = len(sublayers) - 1
                    adjusted_layers[depth].append(item)

        # Calculate layout parameters
        margin = 50
        available_width = width - 2 * margin
        available_height = height - 2 * margin
        base_layer_height = min(25, available_height // (max_depth + 2))
        sublayer_height = base_layer_height * 0.8  # Slightly smaller to fit sublayers

        # SVG generation with interactive controls
        svg_lines = [
            f'<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"'
            f' style="width: 100vw; height: 100vh; position: fixed; top: 0; left: 0; background: white;"'
            f' viewBox="0 0 {width} {height}" preserveAspectRatio="xMidYMid meet">',
            "<defs>",
            "<style>",
            ".frame { stroke: white; stroke-width: 1; cursor: pointer; position: relative; }",
            ".frame:hover { opacity: 0.9; stroke: #333; stroke-width: 2; }",
            "text { font-family: monospace; font-size: 11px; fill: black; pointer-events: none; font-weight: 300; }",
            ".title { font-size: 14px; font-weight: 500; }",
            ".tooltip { opacity: 0; pointer-events: none; position: absolute; }",
            ".frame:hover .tooltip { opacity: 1; }",
            ".timeline-controls { cursor: pointer; }",
            ".zoom-controls { cursor: pointer; }",
            "#mainGroup { transform-box: fill-box; }",
            ".frame { transition: opacity 0.1s; }",
            ".frame:hover { opacity: 0.8; }",
            ".frame text { transform-box: fill-box; transform-origin: center; }",
            "</style>",
            "</defs>",
            f'<rect width="{width}" height="{height}" fill="#f8f9fa"/>',
            f'<rect width="{width}" height="{height}" fill="none" stroke="black" stroke-width="1"/>',
            '<script type="text/javascript"><![CDATA[',
            "let viewportStart = 0;",
            "let viewportWidth = 1.0;",
            "let isDragging = false;",
            "let lastX = 0;",
            "",
            "function initializeControls() {",
            '    const svg = document.querySelector("svg");',
            '    svg.addEventListener("wheel", handleWheel, { passive: false });',
            '    svg.addEventListener("mousedown", startDrag);',
            '    document.addEventListener("mousemove", drag);',
            '    document.addEventListener("mouseup", endDrag);',
            "}",
            "",
            "function handleWheel(event) {",
            "    event.preventDefault();",
            "",
            "    const svg = event.currentTarget;",
            "    const rect = svg.getBoundingClientRect();",
            "    const mouseX = event.clientX - rect.left;",
            "    const relativeX = (mouseX - 50) / (rect.width - 100);  // Adjust for margins",
            "",
            "    // Calculate zoom based on wheel delta",
            "    const zoomFactor = event.deltaY > 0 ? 1.1 : 0.9;",
            "",
            "    // Calculate new viewport width",
            "    const newWidth = Math.max(0.05, Math.min(viewportWidth * zoomFactor, 1.0));",
            "",
            "    // Adjust viewport start to keep mouse position stable",
            "    const mouseViewportX = viewportStart + (relativeX * viewportWidth);",
            "    const newRelativeX = relativeX;  // Keep the same relative position",
            "    viewportStart = mouseViewportX - (newRelativeX * newWidth);",
            "",
            "    // Clamp viewport start",
            "    viewportStart = Math.max(0, Math.min(viewportStart, 1 - newWidth));",
            "    viewportWidth = newWidth;",
            "",
            "    updateTransform();",
            "    updateSpanText();",
            "}",
            "",
            "function startDrag(event) {",
            "    if (event.button !== 0) return;  // Only left mouse button",
            "    isDragging = true;",
            "    lastX = event.clientX;",
            "    event.preventDefault();",
            "}",
            "",
            "function drag(event) {",
            "    if (!isDragging) return;",
            "",
            '    const svg = document.querySelector("svg");',
            "    const rect = svg.getBoundingClientRect();",
            "    const dx = (event.clientX - lastX) / (rect.width - 100);  // Adjust for margins",
            "",
            "    // Move viewport start by the drag amount",
            "    viewportStart -= dx * viewportWidth;",
            "    viewportStart = Math.max(0, Math.min(viewportStart, 1 - viewportWidth));",
            "",
            "    lastX = event.clientX;",
            "    updateTransform();",
            "}",
            "",
            "function endDrag() {",
            "    isDragging = false;",
            "}",
            "",
            "function updateTransform() {",
            '    const mainGroup = document.getElementById("mainGroup");',
            "    const scale = 1 / viewportWidth;",
            '    const translate = -viewportStart * scale * (document.querySelector("svg").getBoundingClientRect().width - 100);',
            "",
            "    // Apply horizontal scale to the group",
            "    mainGroup.style.transform = `translate(${translate}px, 0) scale(${scale}, 1)`;",
            '    mainGroup.style.transformOrigin = "left";',
            "",
            "    // Counter-scale all text elements to maintain their original size",
            '    const frames = mainGroup.querySelectorAll(".frame");',
            "    frames.forEach(frame => {",
            '        const rect = frame.querySelector("rect");',
            '        const text = frame.querySelector("text");',
            "        if (!text) return;",
            "",
            "        // Get the frame width after scaling",
            '        const frameWidth = parseFloat(rect.getAttribute("width"));',
            "        // Position text in the middle of the scaled frame",
            '        text.setAttribute("x", frameWidth / 2);',
            "        // Counter-scale the text",
            "        text.style.transform = `scale(${1/scale}, 1)`;",
            '        text.style.transformOrigin = "center";',
            "    });",
            "",
            "    updateTimeScale();",
            "    updateSpanText();",
            "}",
            "",
            "function updateSpanText() {",
            '    const frames = document.querySelectorAll(".frame");',
            "    const scale = 1 / viewportWidth;",
            "",
            "    frames.forEach(frame => {",
            '        const rect = frame.querySelector("rect");',
            '        const text = frame.querySelector("text");',
            "        if (!text) return;",
            "",
            '        const frameWidth = parseFloat(rect.getAttribute("width")) * scale;',
            "        const minWidthForText = 60;  // Minimum width to show text",
            "        const minWidthForFullText = 120;  // Minimum width to show full text",
            "",
            "        if (frameWidth < minWidthForText) {",
            '            text.style.display = "none";',
            "        } else {",
            '            text.style.display = "";',
            '            const fullText = text.getAttribute("data-full-text") || text.textContent;',
            "",
            "            if (frameWidth < minWidthForFullText) {",
            '                // Show truncated text with "..."',
            "                const maxChars = Math.floor(frameWidth / 6);",
            "                text.textContent = fullText.length > maxChars ? ",
            '                    fullText.substring(0, maxChars-2) + "..." : ',
            "                    fullText;",
            "            } else {",
            "                // Show full text",
            "                text.textContent = fullText;",
            "            }",
            "        }",
            "    });",
            "}",
            "",
            "function updateTimeScale() {",
            '    const timeScale = document.getElementById("timeScale");',
            '    const ticks = timeScale.getElementsByClassName("tick");',
            '    const totalTime = parseFloat(timeScale.getAttribute("data-total-time"));',
            "",
            "    for (let tick of ticks) {",
            '        const time = parseFloat(tick.getAttribute("data-time"));',
            "        const adjustedTime = (time * viewportWidth) + viewportStart;",
            '        const label = tick.getElementsByTagName("text")[0];',
            '        label.textContent = (adjustedTime * totalTime).toFixed(2) + "s";',
            "    }",
            "}",
            "",
            'window.addEventListener("load", initializeControls);',
            "]]></script>",
        ]

        # Create main group for panning/zooming
        svg_lines.append('<g id="mainGroup" transform="scale(1)">')

        # Draw layers from bottom to top
        colors = [
            "#e74c3c",
            "#3498db",
            "#2ecc71",
            "#f39c12",
            "#9b59b6",
            "#1abc9c",
            "#34495e",
            "#e67e22",
            "#95a5a6",
            "#16a085",
            "#27ae60",
            "#2980b9",
        ]

        for depth in sorted(adjusted_layers.keys(), reverse=True):
            items = adjusted_layers[depth]
            base_y = height - margin - (depth + 1) * base_layer_height

            for item in items:
                # Calculate position and width
                start_offset = item["start_time"] - min_start
                x = margin + (start_offset / total_time) * available_width
                w = max((item["duration"] / total_time) * available_width, 1)

                # Calculate y position based on sublayer
                y = base_y + (item.get("sublayer", 0) * sublayer_height)

                # Ensure we don't go outside bounds
                x = max(margin, min(x, width - margin))
                w = min(w, width - margin - x)

                if w < 0.5:  # Skip very thin rectangles
                    continue

                color = colors[depth % len(colors)]

                # Create tooltip text
                tooltip = f"{item['name']}: {item['duration']:.6f}s ({item['duration'] / total_time * 100:.1f}%)"

                # Rectangle with tooltip
                svg_lines.append(
                    f'<g class="frame" transform="translate({x:.2f},{y})">'
                    f'<rect width="{w:.2f}" height="{sublayer_height - 1}" '
                    f'fill="{color}" opacity="0.8">'
                    f"<title>{tooltip}</title>"
                    f"</rect>"
                )

                # Text (only if wide enough)
                if w > 60:
                    text = item["name"]
                    svg_lines.append(
                        f'<text x="{w / 2:.2f}" y="{sublayer_height / 2 + 4}" '
                        f'text-anchor="middle" data-full-text="{text}">{text}</text>'
                    )

                svg_lines.append("</g>")

        svg_lines.append("</g>")  # Close main group

        # Add title
        svg_lines.append(
            f'<text x="{width / 2}" y="25" text-anchor="middle" class="title">'
            f"Flamegraph - Total Time: {total_time:.6f}s</text>"
        )

        # Add time scale at bottom with data attributes for JavaScript
        scale_y = height - margin + 35
        svg_lines.append(f'<g id="timeScale" data-total-time="{total_time}">')

        num_ticks = 10
        for i in range(num_ticks + 1):
            tick_time = i / num_ticks
            tick_x = margin + (i / num_ticks) * available_width

            # Tick mark with data attribute for time
            svg_lines.append(
                f'<g class="tick" data-time="{tick_time}" transform="translate({tick_x},{scale_y})">'
                f'<line y1="-5" y2="5" stroke="#666"/>'
                f'<text y="18" text-anchor="middle" style="font-size: 10px;">'
                f"{(tick_time * total_time):.2f}s</text>"
                f"</g>"
            )

        # Add scale line
        svg_lines.append(
            f'<line x1="{margin}" y1="{scale_y}" x2="{margin + available_width}" y2="{scale_y}" stroke="#666"/>'
        )
        svg_lines.append("</g>")  # Close timeScale group

        svg_lines.append("</svg>")

        try:
            with open(output_file, "w") as f:
                f.write("\n".join(svg_lines))
            print(f"Interactive flamegraph saved to {output_file}")
            print(f"Flamegraph dimensions: {width}x{height}, {max_depth + 1} layers")
        except Exception as e:
            print(f"Error generating flamegraph: {e}")

    def save_trace_json(self, output_file="trace.json"):
        """Save trace data in JSON format for external tools."""
        span_data = self.get_span_data()

        try:
            with open(output_file, "w") as f:
                json.dump(span_data, f, indent=2)
            print(f"Trace data saved to {output_file}")
        except Exception as e:
            print(f"Error saving trace data: {e}")


# Example usage with nested operations
async def my_async_function(profiler):
    """Example async function with nested profiling."""
    async with profiler.profile("my_async_function", {"function_type": "main"}):
        async with profiler.profile("initial_setup"):
            await asyncio.sleep(0.1)

            async with profiler.profile("config_loading"):
                await asyncio.sleep(0.03)

        async with profiler.profile("data_processing"):
            await asyncio.sleep(0.2)

            async with profiler.profile("data_validation"):
                await asyncio.sleep(0.05)

            async with profiler.profile("data_transformation"):
                await asyncio.sleep(0.08)

        async with profiler.profile("finalization"):
            await asyncio.sleep(0.05)

    return "Processing complete!"


async def parallel_work(profiler):
    """Another function to demonstrate parallel operations."""
    async with profiler.profile("parallel_work"):
        async with profiler.profile("network_call"):
            await asyncio.sleep(0.15)

        async with profiler.profile("cache_update"):
            await asyncio.sleep(0.07)


# Example usage with the profiled decorator
profiler = OTelProfiler()


# Example with sync function
@profiler.profiled("sync_example")
def process_data(data: List[int]) -> int:
    time.sleep(0.1)  # Simulate work
    return sum(data)


# Example with async function
@profiler.profiled("async_example")
async def fetch_data(url: str) -> Dict[str, Any]:
    await asyncio.sleep(0.2)  # Simulate network call
    return {"url": url, "status": "success"}


# Example with custom attributes
@profiler.profiled(operation_name="custom_attributes_example", attributes={"type": "computation", "priority": "high"})
def heavy_computation(x: int) -> float:
    time.sleep(0.15)  # Simulate work
    return x * 3.14


# Example without explicit operation name (uses function name)
@profiler.profiled()
async def validate_input(data: Dict[str, Any]) -> bool:
    await asyncio.sleep(0.05)  # Simulate validation
    return True


# Example usage:
async def main():
    # Run sync function
    result1 = process_data([1, 2, 3, 4, 5])
    print(f"Process result: {result1}")

    # Run async function
    result2 = await fetch_data("https://example.com")
    print(f"Fetch result: {result2}")

    # Run with custom attributes
    result3 = heavy_computation(42)
    print(f"Computation result: {result3}")

    # Run without explicit name
    result4 = await validate_input({"key": "value"})
    print(f"Validation result: {result4}")

    # Print profiling results
    profiler.print_results()

    # Save results to files
    profiler.save_results("profile_results.csv")
    profiler.generate_flamegraph_svg("profile_flamegraph.svg")
    profiler.save_trace_json("profile_trace.json")
