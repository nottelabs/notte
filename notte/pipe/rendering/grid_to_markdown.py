from dataclasses import dataclass, field

from notte.browser.dom_tree import DomNode
from notte.browser.node_type import NodeType


def prune_non_grid_nodes(node: DomNode) -> DomNode | None:
    def is_grid(node: DomNode) -> bool:
        return node.get_role_str() == "grid" and node.computed_attributes.in_viewport

    # this step might be optional, can be optional
    dialog_node = node.prune_non_dialogs_if_present()[0]

    grid_nodes = dialog_node.find_all_matching_subtrees_with_parents(dialog_node, is_grid)
    if len(grid_nodes) == 0:
        return None
    return grid_nodes[0]


@dataclass
class GridCell:
    """Represents a cell in the grid with its content and metadata."""

    content: str = ""
    column_index: int | None = None
    is_header: bool = False
    is_hidden: bool = False
    is_selected: bool = False
    texts: list[str] = field(default_factory=list)  # Store all text pieces
    node_id: str | None = None  # Store node ID for interactive elements

    def format_content(self) -> str:
        """Format cell content including all texts and node ID."""
        if not self.texts:
            return self.content

        # Join all unique text pieces
        unique_texts = []
        for text in self.texts:
            if text not in unique_texts:
                unique_texts.append(text)

        # Format with node ID and selection status
        result = " ".join(unique_texts)
        if self.node_id:
            result = f"{self.node_id}[:]{result}"
        if self.is_selected:
            result = f"{result} (selected)"
        return result


@dataclass
class GridRow:
    """Represents a row in the grid."""

    cells: list[GridCell] = field(default_factory=list)
    is_header: bool = False

    def add_cell(self, cell: GridCell) -> None:
        # If cell has column_index, fill gaps with empty cells
        if cell.column_index is not None:
            while len(self.cells) < cell.column_index - 1:
                self.cells.append(GridCell())
        self.cells.append(cell)

    def to_list(self) -> list[str]:
        return [cell.format_content() for cell in self.cells if not cell.is_hidden]


@dataclass
class Grid:
    """Represents the complete grid structure."""

    rows: list[GridRow] = field(default_factory=list)
    current_row: GridRow = field(default_factory=GridRow)
    current_cell: GridCell = field(default_factory=GridCell)

    def add_text_to_current_cell(self, text: str) -> None:
        if text.strip():
            self.current_cell.texts.append(text.strip())

    def finish_current_cell(self) -> None:
        if self.current_cell.texts or not self.current_cell.is_hidden:
            self.current_row.add_cell(self.current_cell)
        self.current_cell = GridCell()

    def finish_current_row(self) -> None:
        self.finish_current_cell()
        if self.current_row.cells:
            self.rows.append(self.current_row)
        self.current_row = GridRow()

    def to_markdown(self) -> str:
        if not self.rows:
            return ""

        # Convert rows to string lists
        string_rows = [row.to_list() for row in self.rows]

        # Filter out empty rows
        string_rows = [row for row in string_rows if row]

        if not string_rows:
            return ""

        # Normalize column count
        max_cols = max(len(row) for row in string_rows)
        string_rows = [row + [""] * (max_cols - len(row)) for row in string_rows]

        # Build markdown table
        header = "| " + " | ".join(string_rows[0]) + " |"
        separator = "|-" + "-|".join(["-" * len(cell) for cell in string_rows[0]]) + "-|"
        body = "\n".join("| " + " | ".join(row) + " |" for row in string_rows[1:])

        return f"{header}\n{separator}\n{body}" if len(string_rows) > 1 else header


def extract_table_rows(
    node: DomNode,
    grid: Grid | None = None,
) -> Grid:
    """
    Recursively extracts table rows as lists of cell values from a grid structure.

    Args:
        node: The current DomNode being processed
        grid: The grid structure being built

    Returns:
        A Grid object containing the structured table data
    """
    if grid is None:
        grid = Grid()

    role = node.get_role_str()

    # Special handling for rowgroup to extract headers
    if role == "rowgroup":
        for child in node.children:
            if child.get_role_str() == "group":
                # First group contains the section title
                header_text = child.inner_text().strip()
                if header_text:
                    header_row = GridRow(is_header=True)
                    header_row.add_cell(GridCell(texts=[header_text], is_header=True))
                    grid.rows.append(header_row)
                break

        # Look for weekday headers in groups (including hidden ones)
        for child in node.children:
            if (
                child.get_role_str() == "group"
                and child.children
                and all(g.get_role_str() == "group" and g.inner_text().strip() for g in child.children)
            ):
                header_row = GridRow(is_header=True)
                for i, header_group in enumerate(child.children, start=1):
                    header_cell = GridCell(texts=[header_group.inner_text().strip()], is_header=True, column_index=i)
                    header_row.add_cell(header_cell)
                if header_row.cells:
                    grid.rows.append(header_row)
                break

    # Handle text nodes and group text
    if node.type == NodeType.TEXT:
        if node.text:
            grid.add_text_to_current_cell(node.text)
        return grid
    elif role == "group" and node.text:
        grid.add_text_to_current_cell(node.text)

    # Handle interactive nodes
    if node.type == NodeType.INTERACTION and node.id:
        grid.current_cell.node_id = node.id

    # Handle node attributes
    if node.attributes is not None:
        # Only apply hidden attribute for non-header cells
        if node.attributes.aria_hidden and not (
            role == "group" and node.parent and node.parent.get_role_str() == "group"
        ):
            grid.current_cell.is_hidden = True
        if node.attributes.aria_colindex is not None:
            grid.current_cell.column_index = node.attributes.aria_colindex
        if node.attributes.aria_selected is not None:
            grid.current_cell.is_selected = node.attributes.aria_selected

    # Process node based on its role
    match role:
        case "row":
            grid.finish_current_row()
        case "cell" | "gridcell":
            grid.finish_current_cell()
        case "columnheader" | "rowheader":
            grid.finish_current_cell()
            grid.current_cell.is_header = True
            grid.current_row.is_header = True

    # Recursively process children
    for child in node.children:
        grid = extract_table_rows(child, grid)

    # Handle end of node processing
    match role:
        case "row":
            grid.finish_current_row()
        case "cell" | "gridcell" | "columnheader" | "rowheader":
            grid.finish_current_cell()

    return grid


def dom_to_markdown_table(root: DomNode) -> str:
    """Converts a DomNode tree into a Markdown table string."""
    if root.get_role_str() != "grid":
        raise ValueError("Root node must be a 'grid' representing a table.")

    grid = extract_table_rows(root)

    # Group rows by sections (determined by single-cell header rows)
    result: list[str] = []
    current_rows: list[str] = []

    for row in grid.rows:
        # If it's a section header (single cell header row)
        if row.is_header and len(row.cells) == 1:
            # Add previous section's table if exists
            if current_rows:
                result.extend(current_rows)
                result.append("")  # Add spacing between sections
            result.append(f"### {row.cells[0].format_content()}")
            current_rows = []
        else:
            # Convert row to markdown format
            cells = row.to_list()
            if cells:  # Skip empty rows
                row_str = "| " + " | ".join(cells) + " |"
                current_rows.append(row_str)
                # Add separator after headers
                if row.is_header and len(current_rows) == 1:
                    separator = "|-" + "-|-".join(["-" * len(cell) for cell in cells]) + "-|"
                    current_rows.append(separator)

    # Add the last section's table
    if current_rows:
        result.extend(current_rows)

    return "\n".join(result)
