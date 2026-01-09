import contextlib
import csv
import functools
import inspect
import json
import time
from collections import defaultdict
from typing import Any, Callable, ParamSpec, TypeVar, cast

# OpenTelemetry imports
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import SpanProcessor
from opentelemetry.sdk.trace import TracerProvider as SDKTracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import Status, StatusCode, Tracer

from notte_core.common.cache import CacheDirectory, ensure_cache_directory
from notte_core.common.config import config
from notte_core.common.logging import logger

P = ParamSpec("P")
R = TypeVar("R")
TP = TypeVar("TP", bound=SDKTracerProvider)


class NotteProfiler:
    """
    OpenTelemetry-based profiler that captures timing data and generates flamegraphs.
    Uses OpenTelemetry spans for instrumentation and exports timing data for visualization.

    Supports multiple service names with separate TracerProviders for each service.
    """

    def __init__(self, default_service_name: str = "default"):
        """
        Initialize the OpenTelemetry profiler.

        Args:
            default_service_name (str): Default service name for general tracing
        """
        self.enable: bool = config.enable_profiling
        self.default_service_name: str = default_service_name

        # Multiple tracer providers for different services
        self._tracer_providers: dict[str, SDKTracerProvider] = {}
        self._tracers: dict[str, Tracer] = {}

        # Shared memory exporter for all services
        self.memory_exporter: InMemorySpanExporter = InMemorySpanExporter()
        self.additional_processors: list[SpanProcessor] = []
        self.enable_memory_exporter: bool = True
        self._tracer_setup_done: bool = False

        # Only setup tracer if profiling is enabled
        # Note: For extensibility, custom processors should be added before first use
        if self.enable:
            self.setup_tracer(default_service_name)

        self.start_time: float | None = None

    def disable_memory_exporter(self) -> None:
        """
        Disable the in-memory span exporter to prevent memory growth.

        Useful when exporting traces to external systems (Tempo, Jaeger, etc.)
        where you don't need local flamegraph generation.

        If called after the tracer is already set up, the memory exporter will be
        removed from all providers. Otherwise, it simply won't be added during setup.

        Example:
            ```python
            from notte_core.profiling import profiler

            # Can be called anytime - even after profiler is initialized
            profiler.disable_memory_exporter()

            # Add your external exporter
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
            from opentelemetry.sdk.trace.export import SimpleSpanProcessor

            otlp_exporter = OTLPSpanExporter(endpoint="http://localhost:4317", insecure=True)
            profiler.add_span_processor(SimpleSpanProcessor(otlp_exporter))
            ```
        """
        was_enabled = self.enable_memory_exporter
        self.enable_memory_exporter = False

        # If tracer is already set up and memory exporter was enabled,
        # we need to shut down memory processors from all providers
        if was_enabled and self._tracer_setup_done:
            if self._tracer_providers:
                try:
                    # Shutdown forces the processor to stop accepting new spans
                    memory_processor = SimpleSpanProcessor(self.memory_exporter)
                    memory_processor.shutdown()
                    logger.info("In-memory span exporter disabled (existing processor shut down for all services)")
                except Exception as e:
                    logger.warning(f"Failed to shutdown memory processor: {e}")
            else:
                logger.info("In-memory span exporter disabled (will not be used in new sessions)")
        else:
            logger.info("In-memory span exporter disabled to prevent memory growth")

    def add_span_processor(self, processor: SpanProcessor, service_name: str | None = None) -> None:
        """
        Add an additional span processor to export traces to external systems.

        This method allows extending the profiler with custom exporters without
        modifying the core code. Useful for adding Tempo, Jaeger, Pyroscope, etc.

        Args:
            processor: An OpenTelemetry SpanProcessor instance
            service_name: If provided, only adds to that service. If None, adds to all services.

        Example:
            ```python
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
            from opentelemetry.sdk.trace.export import SimpleSpanProcessor

            otlp_exporter = OTLPSpanExporter(endpoint="http://localhost:4317", insecure=True)
            profiler.add_span_processor(SimpleSpanProcessor(otlp_exporter))
            ```
        """
        if not self.enable:
            logger.warning("Profiling is disabled. Span processor will not be used.")
            return

        self.additional_processors.append(processor)

        # Add processor to existing providers
        if service_name is not None:
            # Add to specific service
            if service_name in self._tracer_providers:
                self._tracer_providers[service_name].add_span_processor(processor)
                logger.info(f"Added span processor to service '{service_name}': {processor.__class__.__name__}")
            else:
                logger.warning(f"Service '{service_name}' not set up yet. Processor will be added during setup.")
        else:
            # Add to all existing services
            if self._tracer_providers:
                for svc_name, provider in self._tracer_providers.items():
                    provider.add_span_processor(processor)
                    logger.info(f"Added span processor to service '{svc_name}': {processor.__class__.__name__}")
            else:
                logger.warning("No tracer providers set up yet. Processor will be added during setup.")

    def setup_tracer(self, service_name: str) -> None:
        """
        Set up OpenTelemetry tracer for a specific service.

        Args:
            service_name: The name of the service to create a tracer for
        """
        # Don't recreate if already exists
        if service_name in self._tracer_providers:
            return

        resource = Resource.create({"service.name": service_name})

        # Create tracer provider for this service
        provider = SDKTracerProvider(resource=resource)

        # Add memory exporter to collect spans - use immediate export (unless disabled)
        if self.enable_memory_exporter:
            span_processor = SimpleSpanProcessor(self.memory_exporter)
            provider.add_span_processor(span_processor)
        else:
            logger.info(f"Memory exporter disabled for service '{service_name}' - spans will not be stored in memory")

        # Add any additional processors that were registered
        for processor in self.additional_processors:
            provider.add_span_processor(processor)
            logger.info(f"Added span processor to service '{service_name}': {processor.__class__.__name__}")

        # Store the provider for this service
        self._tracer_providers[service_name] = provider

        # Get tracer for this service
        self._tracers[service_name] = provider.get_tracer(__name__)

        # Set the first provider as global (for backward compatibility)
        if not self._tracer_setup_done:
            trace.set_tracer_provider(provider)
            self._tracer_setup_done = True

        logger.info(f"Tracer setup complete for service: {service_name}")

    def get_tracer(self, service_name: str | None = None) -> Tracer:
        """
        Get a tracer for a specific service, creating it if necessary.

        Args:
            service_name: Service name to get tracer for. If None, uses default service.

        Returns:
            Tracer for the specified service
        """
        if service_name is None:
            service_name = self.default_service_name

        # Setup tracer for this service if not already done
        if service_name not in self._tracers:
            if self.enable:
                self.setup_tracer(service_name)
            else:
                # Return no-op tracer if profiling is disabled
                return trace.get_tracer(__name__)

        return self._tracers[service_name]

    @contextlib.asynccontextmanager
    async def profile(
        self, operation_name: str, attributes: dict[str, Any] | None = None, service_name: str | None = None
    ):
        """
        Context manager for profiling a section of code using OpenTelemetry spans.

        Args:
            operation_name (str): Name of the operation being profiled
            attributes (dict, optional): Additional attributes to attach to the span
            service_name (str, optional): Service name for this span. If None, uses default.
        """
        if not self.enable:
            yield None
            return

        if self.start_time is None:
            self.start_time = time.perf_counter()

        tracer = self.get_tracer(service_name)
        with tracer.start_as_current_span(operation_name) as span:
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
    def profile_sync(
        self, operation_name: str, attributes: dict[str, Any] | None = None, service_name: str | None = None
    ):
        """
        Synchronous context manager for profiling a section of code using OpenTelemetry spans.

        Args:
            operation_name (str): Name of the operation being profiled
            attributes (dict, optional): Additional attributes to attach to the span
            service_name (str, optional): Service name for this span. If None, uses default.
        """
        if not self.enable:
            yield None
            return

        if self.start_time is None:
            self.start_time = time.perf_counter()

        tracer = self.get_tracer(service_name)
        with tracer.start_as_current_span(operation_name) as span:
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
        self,
        operation_name: str | None = None,
        attributes: dict[str, Any] | None = None,
        service_name: str | None = None,
    ) -> Callable[[Callable[P, R]], Callable[P, R]]:
        """
        Decorator that profiles a function using OpenTelemetry spans.
        Works with both synchronous and asynchronous functions.

        For class methods, uses the full qualified name (classname.functionname) as the operation name
        unless a custom name is provided.

        Args:
            operation_name (str, optional): Name of the operation. Defaults to the qualified function name.
            attributes (dict, optional): Additional attributes to attach to the span.
            service_name (str, optional): Service name for this span. If None, uses default.
                                          Options: "default", "execution", "observation", "llm"

        Returns:
            Callable: Wrapped function with profiling

        Example:
            ```python
            # Use default service
            @profiler.profiled()
            async def my_function():
                pass

            # Use specific service
            @profiler.profiled(service_name="llm")
            async def call_llm():
                pass
            ```
        """
        # Handle case where decorator is used without parentheses
        if callable(operation_name):
            func = operation_name
            return self.profiled()(func)

        def decorator(func: Callable[P, R]) -> Callable[P, R]:
            # If profiling is disabled, return the original function
            if not self.enable:
                return func

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
                    async with self.profile(op_name, attributes, service_name):
                        return await func(*args, **kwargs)

                return cast(Callable[P, R], async_wrapper)  # pyright: ignore[reportInvalidCast]

            # Handle sync functions
            else:

                @functools.wraps(func)
                def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
                    with self.profile_sync(op_name, attributes, service_name):
                        return func(*args, **kwargs)

                return cast(Callable[P, R], sync_wrapper)  # pyright: ignore[reportInvalidCast]

        return decorator

    def get_span_data(self) -> list[dict[str, Any]]:
        """
        Extract span data from the exporter.

        Returns empty list if memory exporter is disabled.
        """
        if not self.enable_memory_exporter:
            logger.warning("Memory exporter is disabled. No span data available for flamegraph generation.")
            return []

        spans = self.memory_exporter.get_finished_spans()
        span_data: list[dict[str, Any]] = []

        for span in spans:
            if span.context is None:
                continue

            # Convert nanoseconds to seconds, handle potential None values
            start_time = span.start_time / 1_000_000_000 if span.start_time is not None else 0
            end_time = span.end_time / 1_000_000_000 if span.end_time is not None else 0
            duration = end_time - start_time

            span_info = {
                "name": span.name,
                "trace_id": span.context.trace_id,
                "span_id": span.context.span_id,
                "parent_id": span.parent.span_id if span.parent else None,
                "start_time": start_time,
                "end_time": end_time,
                "duration": duration,
                "attributes": dict(span.attributes) if span.attributes else {},
                "status": span.status.status_code if span.status else StatusCode.UNSET,
            }
            span_data.append(span_info)

        return span_data

    def build_span_hierarchy(self, span_data: list[dict[str, Any]]) -> list[dict[str, Any]]:
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

    def generate_stack_paths(self, span_data: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Generate stack paths for flamegraph from span hierarchy."""
        hierarchy = self.build_span_hierarchy(span_data)
        flamegraph_data: list[dict[str, Any]] = []

        def traverse_spans(spans: list[dict[str, Any]], path_stack: list[str] | None = None) -> None:
            path_stack = path_stack or []

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

    def save_results(self, output_file: str | None = None) -> None:
        """Save profiling results to CSV.

        Args:
            output_file: Path to output CSV file. If None, uses cache directory.
                        If relative path, uses it relative to cwd.
                        If absolute path, uses it as-is.
        """
        if not self.enable:
            raise RuntimeError("Profiling is disabled. Enable it by setting enable_profiling=True in your config.")

        # Use cache directory if no output file specified
        if output_file is None:
            profiling_dir = ensure_cache_directory(CacheDirectory.PROFILING)
            output_file = str(profiling_dir / "otel_profile_results.csv")

        span_data = self.get_span_data()
        flamegraph_data = self.generate_stack_paths(span_data)

        try:
            with open(output_file, "w", newline="") as csvfile:
                fieldnames = ["name", "stack_path", "start_time", "end_time", "duration", "depth"]
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(flamegraph_data)
        except Exception as e:
            logger.error(f"Error saving results: {e}")

    def print_results(self) -> None:
        """Print hierarchical profiling results."""
        if not self.enable:
            raise RuntimeError("Profiling is disabled. Enable it by setting enable_profiling=True in your config.")

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

    def generate_flamegraph_svg(self, output_file: str | None = None, width: int = 1200, height: int = 600) -> None:
        """Generate a traditional dark flamegraph with compact layout.

        Args:
            output_file: Path to output SVG file. If None, uses cache directory.
                        If relative path, uses it relative to cwd.
                        If absolute path, uses it as-is.
            width: Width of the SVG in pixels.
            height: Height of the SVG in pixels.
        """
        if not self.enable:
            raise RuntimeError("Profiling is disabled. Enable it by setting enable_profiling=True in your config.")

        # Use cache directory if no output file specified
        if output_file is None:
            profiling_dir = ensure_cache_directory(CacheDirectory.PROFILING)
            output_file = str(profiling_dir / "flamegraph.svg")

        span_data = self.get_span_data()
        flamegraph_data = self.generate_stack_paths(span_data)

        if not flamegraph_data:
            logger.error("No data to generate flamegraph")
            return

        # Find the overall time bounds
        min_start = min(item["start_time"] for item in flamegraph_data)
        max_end = max(item["end_time"] for item in flamegraph_data)
        total_time = max_end - min_start

        if total_time <= 0:
            logger.error("No meaningful timing data for flamegraph")
            return

        # Calculate total time per function name
        function_total_times: defaultdict[str, float] = defaultdict(float)
        for item in flamegraph_data:
            function_total_times[item["name"]] += item["duration"]

        # Second pass: handle overlapping spans by adjusting vertical position
        adjusted_layers: defaultdict[int, list[dict[str, Any]]] = defaultdict(list)
        max_sublayers: defaultdict[int, int] = defaultdict(int)  # Track max sublayers per depth

        # Build span ID to span mapping for quick lookups
        span_map: dict[str, dict[str, Any]] = {span["span_id"]: span for span in span_data}

        # Calculate actual stack depth for each span by following parent chain
        def calculate_depth(span: dict[str, Any]) -> int:
            depth = 0
            current_span = span
            while current_span.get("parent_id"):
                parent_id = current_span["parent_id"]
                if parent_id in span_map:
                    depth += 1
                    current_span = span_map[parent_id]
                else:
                    break  # Parent not found, stop counting
            return depth

        # Update span data with actual stack depths
        for span in span_data:
            span["depth"] = calculate_depth(span)

        # Group spans by depth for layout
        max_depth = max(span["depth"] for span in span_data)
        for depth in range(max_depth + 1):
            depth_spans = [s for s in span_data if s["depth"] == depth]
            sorted_spans = sorted(depth_spans, key=lambda x: x["start_time"])

            # Track occupied time ranges at each sublayer
            sublayers: list[list[tuple[float, float]]] = []

            for item in sorted_spans:
                # Find a sublayer where this item doesn't overlap
                placed = False
                for sublayer_idx, sublayer in enumerate(sublayers):
                    # Check if item overlaps with any span in this sublayer
                    overlaps = False
                    for start, end in sublayer:
                        # Consider small gaps as non-overlapping
                        if not (item["end_time"] <= start + 0.000001 or item["start_time"] >= end - 0.000001):
                            overlaps = True
                            break

                    if not overlaps:
                        # Place item in this sublayer
                        sublayer.append((item["start_time"], item["end_time"]))
                        item["sublayer"] = sublayer_idx
                        adjusted_layers[depth].append(item)
                        max_sublayers[depth] = max(max_sublayers[depth], sublayer_idx + 1)
                        placed = True
                        break

                if not placed:
                    # Create new sublayer
                    sublayers.append([(item["start_time"], item["end_time"])])
                    item["sublayer"] = len(sublayers) - 1
                    adjusted_layers[depth].append(item)
                    max_sublayers[depth] = max(max_sublayers[depth], len(sublayers))

        # Calculate layout parameters with dynamic sublayer spacing
        margin = 20
        title_space = 80  # Space for title at top
        available_width = width - 2 * margin
        available_height = height - title_space - 40  # Space for title and bottom margin

        # Calculate base layer height based on max sublayers
        max_total_sublayers = sum(max_sublayers.values())
        base_layer_height = min(18, available_height / (max_total_sublayers + len(max_sublayers)))
        sublayer_height = base_layer_height * 0.9  # Slightly reduce height for visual separation

        # Calculate cumulative sublayer offsets
        cumulative_sublayers: dict[int, int] = defaultdict(int)
        for d in range(max(adjusted_layers.keys()) + 1):
            if d > 0:
                cumulative_sublayers[d] = cumulative_sublayers[d - 1] + max_sublayers[d - 1]

        # SVG generation with dark theme
        svg_lines: list[str] = [
            f'<svg width="{width}" height="{height + 30}" xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"'
            + ' style="width: 100vw; height: 100vh; position: fixed; top: 0; left: 0; background: #1a1a1a;"'
            + f' viewBox="0 0 {width} {height + 30}" preserveAspectRatio="xMidYMid meet">',
            "<defs>",
            "<style>",
            ".frame { cursor: pointer; }",
            ".frame:hover rect { opacity: 0.85; }",
            "text { font-family: 'Verdana', sans-serif; font-size: 10px; fill: #000; pointer-events: none; font-weight: 400; }",
            "#customTooltip text { fill: #ffffff !important; }",
            ".title { font-size: 18px; font-weight: 600; fill: #fff; }",
            ".frame title { pointer-events: auto; }",
            ".grid-line { stroke: #444; stroke-width: 0.5; }",
            ".grid-text { fill: #888; font-size: 8px; }",
            ".timeline-controls { cursor: pointer; }",
            ".zoom-controls { cursor: pointer; }",
            "#mainGroup { transform-box: fill-box; }",
            ".frame { transition: none; }",
            ".frame:hover { filter: brightness(1.1); }",
            ".frame text { transform-box: fill-box; transform-origin: center; dominant-baseline: central; }",
            ".scale-text { fill: #ccc; font-size: 9px; }",
            "svg { text-rendering: geometricPrecision; shape-rendering: crispEdges; }",
            ".frame text { -webkit-font-smoothing: antialiased; backface-visibility: hidden; }",
            "</style>",
            "</defs>",
            f'<rect width="{width}" height="{height + 30}" fill="#1a1a1a"/>',
            f'<text x="{width / 2}" y="20" text-anchor="middle" class="title">' + f"{total_time:.6f}s</text>",
            '<script type="text/javascript"><![CDATA[',
            "let viewportStart = 0;",
            "let viewportWidth = 1.0;",
            "let isDragging = false;",
            "let lastX = 0;",
            "",
            "function setupHoverEffects() {",
            '    const svg = document.querySelector("svg");',
            "    let currentTooltip = null;",
            "    let currentFrame = null;",
            "",
            "    function showTooltip(frame, mouseEvent) {",
            "        if (currentFrame === frame) return;  // Already showing for this frame",
            "",
            "        hideTooltip();",
            "        currentFrame = frame;",
            "",
            "        const tooltipText = frame.getAttribute('data-tooltip');",
            "        if (!tooltipText) return;",
            "",
            "        // Get mouse position relative to SVG",
            "        const svgRect = svg.getBoundingClientRect();",
            "        const mouseX = mouseEvent.clientX - svgRect.left;",
            "        const mouseY = mouseEvent.clientY - svgRect.top;",
            "",
            "        // Calculate tooltip dimensions more precisely",
            "        const padding = 6;",
            "        const charWidth = 5.4;",
            "        const tooltipWidth = Math.min(Math.ceil(tooltipText.length * charWidth) + padding * 2, 400);",
            "        const tooltipHeight = 20;",
            "",
            "        // Position tooltip near mouse but keep it visible",
            "        let tooltipX = mouseX + 2;",
            "        let tooltipY = mouseY - 150;",
            "",
            "        // Keep tooltip within SVG bounds",
            "        if (tooltipX + tooltipWidth > svgRect.width - 10) {",
            "            tooltipX = mouseX - tooltipWidth - 2;",
            "        }",
            "        if (tooltipY < 10) {",
            "            tooltipY = mouseY + 8;",
            "        }",
            "",
            "        // Create tooltip group",
            "        currentTooltip = document.createElementNS('http://www.w3.org/2000/svg', 'g');",
            "        currentTooltip.setAttribute('id', 'customTooltip');",
            "",
            "        // Create background",
            "        const bg = document.createElementNS('http://www.w3.org/2000/svg', 'rect');",
            "        bg.setAttribute('x', tooltipX);",
            "        bg.setAttribute('y', tooltipY);",
            "        bg.setAttribute('width', tooltipWidth);",
            "        bg.setAttribute('height', tooltipHeight);",
            "        bg.setAttribute('fill', '#2a2a2a');",
            "        bg.setAttribute('stroke', '#555');",
            "        bg.setAttribute('stroke-width', '1');",
            "        bg.setAttribute('rx', '4');",
            "        bg.setAttribute('opacity', '0.95');",
            "",
            "        // Create text with precise centering",
            "        const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');",
            "        text.setAttribute('x', tooltipX + tooltipWidth/2);",
            "        text.setAttribute('y', tooltipY + tooltipHeight/2);",
            "        text.setAttribute('fill', '#ffffff');",
            "        text.setAttribute('font-size', '11px');",
            "        text.setAttribute('font-family', 'monospace');",
            "        text.setAttribute('text-anchor', 'middle');",
            "        text.setAttribute('dominant-baseline', 'central');",
            "        text.textContent = tooltipText;",
            "",
            "        currentTooltip.appendChild(bg);",
            "        currentTooltip.appendChild(text);",
            "        svg.appendChild(currentTooltip);",
            "    }",
            "",
            "    function hideTooltip() {",
            "        if (currentTooltip) {",
            "            currentTooltip.remove();",
            "            currentTooltip = null;",
            "        }",
            "        currentFrame = null;",
            "    }",
            "",
            "    // Use mousemove for better tracking",
            '    svg.addEventListener("mousemove", (e) => {',
            '        const frame = e.target.closest(".frame");',
            "        if (frame) {",
            "            showTooltip(frame, e);",
            "        } else {",
            "            hideTooltip();",
            "        }",
            "    });",
            "",
            '    svg.addEventListener("mouseleave", () => {',
            "        hideTooltip();",
            "    });",
            "}",
            "",
            "function initializeControls() {",
            '    const svg = document.querySelector("svg");',
            '    svg.addEventListener("wheel", handleWheel, { passive: false });',
            '    svg.addEventListener("mousedown", startDrag);',
            '    document.addEventListener("mousemove", drag);',
            '    document.addEventListener("mouseup", endDrag);',
            "    updateGridLines();  // Initialize grid lines",
            "    setupHoverEffects();  // Setup custom hover and tooltips",
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
            "    // Round transform values to avoid subpixel rendering issues",
            "    const roundedTranslate = Math.round(translate * 100) / 100;",
            "    const roundedScale = Math.round(scale * 1000) / 1000;",
            "",
            "    // Apply transform with pixel snapping",
            "    requestAnimationFrame(() => {",
            "        mainGroup.style.transform = `translate3d(${roundedTranslate}px, 0, 0) scale3d(${roundedScale}, 1, 1)`;",
            '        mainGroup.style.transformOrigin = "left";',
            "    });",
            "",
            "    updateTimeScale();",
            "    updateSpanText();",
            "    updateGridLines();",
            "}",
            "",
            "function updateSpanText() {",
            '    const frames = document.querySelectorAll(".frame");',
            '    const svg = document.querySelector("svg");',
            "    const svgRect = svg.getBoundingClientRect();",
            "",
            "    frames.forEach(frame => {",
            '        const rect = frame.querySelector("rect");',
            '        let text = frame.querySelector("text");',
            '        const fullText = frame.getAttribute("data-text-content");',
            "",
            "        if (!fullText) return;",
            "",
            "        // Create text element if it doesn't exist",
            "        if (!text) {",
            '            text = document.createElementNS("http://www.w3.org/2000/svg", "text");',
            '            text.setAttribute("text-anchor", "middle");',
            '            text.style.fontFamily = "Verdana, sans-serif";',
            '            text.style.fontSize = "10px";',
            '            text.style.fill = "#000";',
            '            text.style.pointerEvents = "none";',
            '            text.style.fontWeight = "400";',
            '            text.style.dominantBaseline = "central";',
            "            frame.appendChild(text);",
            "        }",
            "",
            "        // Get the actual rendered size of the rectangle on screen",
            "        const rectBBox = rect.getBoundingClientRect();",
            "        const actualWidth = rectBBox.width;",
            "        const actualHeight = rectBBox.height;",
            "",
            "        // Position text in center of original rectangle coordinates",
            '        const rectWidth = parseFloat(rect.getAttribute("width"));',
            '        const rectHeight = parseFloat(rect.getAttribute("height"));',
            '        text.setAttribute("x", rectWidth / 2);',
            '        text.setAttribute("y", rectHeight / 2);',
            "",
            "        // Apply counter-scaling to maintain readable text size",
            "        const scale = 1 / viewportWidth;",
            "        // Round scale to 3 decimal places and ensure pixel-perfect positioning",
            "        const roundedScale = Math.round((1/scale) * 1000) / 1000;",
            "        text.style.transform = `scale(${roundedScale}, 1)`;",
            '        text.style.transformOrigin = "center";',
            "",
            "        // Minimum sizes for showing text (use actual screen pixels)",
            "        const minWidth = 20;   // Minimum pixels wide",
            "        const minHeight = 10;  // Minimum pixels tall",
            "",
            "        if (actualWidth < minWidth || actualHeight < minHeight) {",
            "            // Too small for any text",
            '            text.textContent = "";',
            '            text.style.display = "none";',
            "        } else {",
            '            text.style.display = "block";',
            "",
            "            // Calculate how many characters can fit in the actual screen space",
            "            // Account for some padding on sides",
            "            const availableWidth = actualWidth - 6;  // 3px padding each side",
            "            const avgCharWidth = 5.5;  // Average character width for Verdana 10px",
            "            const maxChars = Math.floor(availableWidth / avgCharWidth);",
            "",
            "            let displayText = '';",
            "            if (maxChars <= 0) {",
            "                displayText = '';",
            "            } else if (maxChars >= fullText.length) {",
            "                displayText = fullText;",
            "            } else if (maxChars >= 4) {",
            '                displayText = fullText.substring(0, maxChars - 3) + "...";',
            "            } else if (maxChars >= 3) {",
            '                displayText = "...";',
            "            } else if (maxChars >= 1) {",
            "                displayText = fullText.substring(0, 1);",
            "            }",
            "",
            "            text.textContent = displayText;",
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
            "function updateGridLines() {",
            '    const gridContainer = document.getElementById("gridLines");',
            '    const svg = document.querySelector("svg");',
            "    const svgRect = svg.getBoundingClientRect();",
            "    const margin = 20;",
            "    const availableWidth = svgRect.width - 2 * margin;",
            "    const availableHeight = svgRect.height - 40;",
            '    const totalTime = parseFloat(document.getElementById("timeScale").getAttribute("data-total-time"));',
            "",
            "    // Clear existing grid lines",
            '    gridContainer.innerHTML = "";',
            "",
            "    // Calculate appropriate grid interval based on zoom level",
            "    const visibleTime = totalTime * viewportWidth;",
            "    let gridInterval;",
            "",
            "    if (visibleTime > 10) gridInterval = 2;",
            "    else if (visibleTime > 5) gridInterval = 1;",
            "    else if (visibleTime > 2) gridInterval = 0.5;",
            "    else if (visibleTime > 1) gridInterval = 0.2;",
            "    else if (visibleTime > 0.5) gridInterval = 0.1;",
            "    else if (visibleTime > 0.2) gridInterval = 0.05;",
            "    else if (visibleTime > 0.1) gridInterval = 0.02;",
            "    else gridInterval = 0.01;",
            "",
            "    // Calculate visible time range",
            "    const startTime = viewportStart * totalTime;",
            "    const endTime = (viewportStart + viewportWidth) * totalTime;",
            "",
            "    // Find first grid line",
            "    const firstGridTime = Math.ceil(startTime / gridInterval) * gridInterval;",
            "",
            "    // Draw grid lines - positioned to align with the scaled content",
            "    const scale = 1 / viewportWidth;",
            "    const translateX = -viewportStart * scale * availableWidth;",
            "",
            "    for (let time = firstGridTime; time <= endTime; time += gridInterval) {",
            "        const normalizedTime = time / totalTime;",
            "        // Position relative to the original coordinate system",
            "        const baseX = margin + normalizedTime * availableWidth;",
            "        // Apply the same transform as the main group",
            "        const x = baseX * scale + translateX;",
            "",
            "        // Only draw if within visible area",
            "        if (x >= margin - 5 && x <= svgRect.width - margin + 5) {",
            "            // Create vertical grid line",
            '            const line = document.createElementNS("http://www.w3.org/2000/svg", "line");',
            '            line.setAttribute("x1", x);',
            '            line.setAttribute("y1", 75);',  # 25 + 50 for title space
            '            line.setAttribute("x2", x);',
            '            line.setAttribute("y2", availableHeight + 75);',
            '            line.setAttribute("class", "grid-line");',
            "            gridContainer.appendChild(line);",
            "",
            "            // Add time label at top",
            '            const text = document.createElementNS("http://www.w3.org/2000/svg", "text");',
            '            text.setAttribute("x", x);',
            '            text.setAttribute("y", 70);',  # Increased from 65 to match new title_space
            '            text.setAttribute("text-anchor", "middle");',
            '            text.setAttribute("class", "grid-text");',
            '            text.textContent = time.toFixed(time < 0.1 ? 3 : time < 1 ? 2 : 1) + "s";',
            "            gridContainer.appendChild(text);",
            "        }",
            "    }",
            "}",
            "",
            'window.addEventListener("load", initializeControls);',
            "]]></script>",
        ]

        # Add vertical grid lines (outside scaled group so they don't get distorted)
        svg_lines.append('<g id="gridLines"></g>')

        # Add hover overlay (outside scaled group to maintain stroke width)
        svg_lines.append('<g id="hoverOverlay"></g>')

        # Create main group for panning/zooming
        svg_lines.append('<g id="mainGroup" transform="scale(1)">')

        # Update color scheme to be more visually appealing while maintaining distinctness
        colors = [
            "#FF7043",  # Deep Orange - Top level operations
            "#FFB74D",  # Orange - Main steps
            "#9575CD",  # Deep Purple - Structured completions
            "#4FC3F7",  # Light Blue - Single completions
            "#81C784",  # Light Green - Browser actions
            "#FF8A65",  # Light Orange - Other operations
        ]

        for depth in sorted(adjusted_layers.keys(), reverse=True):
            items = adjusted_layers[depth]
            # base_y = height - margin - (depth + 1) * base_layer_height

            for item in items:
                # Calculate position and width
                start_offset = item["start_time"] - min_start
                x = margin + (start_offset / total_time) * available_width
                w = max((item["duration"] / total_time) * available_width, 1)

                # Calculate y position based on cumulative sublayers
                base_offset = cumulative_sublayers[depth] * sublayer_height
                y = title_space + base_offset + (item.get("sublayer", 0) * sublayer_height)

                # Ensure we don't go outside bounds
                x = max(margin, min(x, width - margin))
                w = min(w, width - margin - x)

                if w < 0.5:  # Skip very thin rectangles
                    continue

                color = colors[depth % len(colors)]

                # Format duration based on size
                duration_str = f"{item['duration']:.1e}s" if item["duration"] < 0.001 else f"{item['duration']:.1f}s"

                # Calculate total percentage for this function across all runs
                total_func_time = function_total_times[item["name"]]
                total_func_pct = (total_func_time / total_time) * 100
                current_pct = (item["duration"] / total_time) * 100

                # Create tooltip text with both current and total percentages
                tooltip = f"{item['name']}: {duration_str} (this: {current_pct:.1f}%, total: {total_func_pct:.1f}%)"

                # Rectangle with small gap for separation
                # Store text content as data attribute for zoom functionality
                gap = 0.5  # Small gap between blocks
                svg_lines.append(
                    f'<g class="frame" data-text-content="{item["name"]}" data-tooltip="{tooltip}" transform="translate({x:.2f},{y})">'
                    + f'<rect width="{w - gap:.2f}" height="{sublayer_height - gap}" '
                    + f'fill="{color}" stroke="#1a1a1a" stroke-width="0.3" opacity="0.8">'
                    + "</rect>"
                )

                # Text (only if wide enough initially) - smaller threshold for compact layout
                if w > 40:
                    text = item["name"]
                    svg_lines.append(
                        f'<text x="{w / 2:.2f}" y="{sublayer_height / 2:.2f}" '
                        + f'text-anchor="middle" dominant-baseline="central" data-full-text="{text}">{text}</text>'
                    )

                svg_lines.append("</g>")

        svg_lines.append("</g>")  # Close main group

        # Title is already added at the top of the SVG

        # Add time scale at bottom with data attributes for JavaScript
        scale_y = height + 35  # Move scale line much lower to avoid intersecting blocks
        svg_lines.append(f'<g id="timeScale" data-total-time="{total_time}">')

        num_ticks = 10
        for i in range(num_ticks + 1):
            tick_time = i / num_ticks
            tick_x = margin + (i / num_ticks) * available_width

            # Tick mark with data attribute for time
            svg_lines.append(
                f'<g class="tick" data-time="{tick_time}" transform="translate({tick_x},{scale_y})">'
                + '<line y1="-3" y2="3" stroke="#888"/>'
                + '<text y="15" text-anchor="middle" class="scale-text">'
                + f"{(tick_time * total_time):.2f}s</text>"
                + "</g>"
            )

        # Add scale line
        svg_lines.append(
            f'<line x1="{margin}" y1="{scale_y}" x2="{margin + available_width}" y2="{scale_y}" stroke="#888"/>'
        )
        svg_lines.append("</g>")  # Close timeScale group

        svg_lines.append("</svg>")

        try:
            with open(output_file, "w") as f:
                _ = f.write("\n".join(svg_lines))
        except Exception as e:
            logger.error(f"Error generating flamegraph: {e}")

    def save_trace_json(self, output_file: str | None = None) -> None:
        """Save trace data in JSON format for external tools.

        Args:
            output_file: Path to output JSON file. If None, uses cache directory.
                        If relative path, uses it relative to cwd.
                        If absolute path, uses it as-is.
        """
        if not self.enable:
            raise RuntimeError("Profiling is disabled. Enable it by setting enable_profiling=True in your config.")

        # Use cache directory if no output file specified
        if output_file is None:
            profiling_dir = ensure_cache_directory(CacheDirectory.PROFILING)
            output_file = str(profiling_dir / "trace.json")

        span_data = self.get_span_data()

        try:
            with open(output_file, "w") as f:
                json.dump(span_data, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving trace data: {e}")

    def reset(self) -> None:
        """
        Reset the profiler by clearing all collected spans and resetting the start time.
        This allows the profiler to be reused for new profiling sessions.
        Note: The tracer provider cannot be overridden once set, so we only clear the spans.
        """
        if not self.enable:
            logger.warning("Profiling is disabled. Reset operation has no effect.")
            return

        # Clear all collected spans from the memory exporter (if enabled)
        if self.enable_memory_exporter:
            self.memory_exporter.clear()
            logger.info("Profiler reset successfully. All collected spans have been cleared.")
        else:
            logger.info("Profiler reset (memory exporter disabled, no spans to clear).")

        # Reset the start time
        self.start_time = None


# Service name constants for convenience
SERVICE_DEFAULT = "default"
SERVICE_EXECUTION = "execution"
SERVICE_OBSERVATION = "observation"
SERVICE_LLM = "llm"

# Global profiler instance
profiler = NotteProfiler(default_service_name=SERVICE_DEFAULT)
