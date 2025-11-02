from __future__ import annotations

import datetime as dt
import re
import subprocess
from pathlib import Path

from notte_core.common.logging import logger


class WorkflowMetadata:
    """Represents workflow metadata stored in a Python file."""

    workflow_id: str | None
    name: str | None
    description: str | None
    author: str | None
    creation_date: str | None
    last_update_date: str | None

    def __init__(
        self,
        workflow_id: str | None = None,
        name: str | None = None,
        description: str | None = None,
        author: str | None = None,
        creation_date: str | None = None,
        last_update_date: str | None = None,
    ):
        self.workflow_id = workflow_id
        self.name = name
        self.description = description
        self.author = author
        self.creation_date = creation_date
        self.last_update_date = last_update_date

    @classmethod
    def from_file(cls, file_path: Path) -> WorkflowMetadata | None:
        """
        Parse metadata from a Python file.

        Args:
            file_path: Path to the Python file.

        Returns:
            WorkflowMetadata if found, None otherwise.
        """
        try:
            content = file_path.read_text(encoding="utf-8")
            return cls.from_string(content)
        except Exception as e:
            logger.debug(f"Failed to read metadata from {file_path}: {e}")
            return None

    @classmethod
    def from_string(cls, content: str) -> WorkflowMetadata | None:
        """
        Parse metadata from file content string.

        Args:
            content: The file content.

        Returns:
            WorkflowMetadata if found, None otherwise.
        """
        # Look for the metadata block - match from start of file
        lines = content.split("\n")
        metadata_start = None
        for i, line in enumerate(lines):
            if line.strip() == "#!/notte/workflow":
                metadata_start = i
                break

        if metadata_start is None:
            return None

        metadata = cls()

        # Parse lines after the metadata marker
        for i in range(metadata_start + 1, len(lines)):
            line = lines[i].strip()

            # Stop at first non-comment, non-empty line after metadata block
            if line and not line.startswith("#"):
                # Check if we've seen any metadata fields
                if metadata.workflow_id or metadata.name:
                    break
                continue

            # Skip empty comment lines
            if line in ("#", ""):
                continue

            # Parse field lines: # key: value
            if line.startswith("#"):
                # Remove leading #
                content_line = line[1:].strip()
                if ":" in content_line:
                    key, value = content_line.split(":", 1)
                    key = key.strip()
                    value = value.strip()

                    if key == "workflow_id":
                        metadata.workflow_id = value
                    elif key == "name":
                        metadata.name = value
                    elif key == "description":
                        metadata.description = value
                    elif key == "author":
                        metadata.author = value
                    elif key == "creation_date":
                        metadata.creation_date = value
                    elif key == "last_update_date":
                        metadata.last_update_date = value

        return metadata if metadata.workflow_id or metadata.name else None

    def to_block(self) -> str:
        """
        Convert metadata to a metadata block string.

        Returns:
            The metadata block as a string.
        """
        lines = ["#!/notte/workflow", "#"]
        if self.workflow_id:
            lines.append(f"# workflow_id: {self.workflow_id}")
        if self.name:
            lines.append(f"# name: {self.name}")
        if self.description:
            lines.append(f"# description: {self.description}")
        if self.author:
            lines.append(f"# author: {self.author}")
        if self.creation_date:
            lines.append(f"# creation_date: {self.creation_date}")
        if self.last_update_date:
            lines.append(f"# last_update_date: {self.last_update_date}")
        return "\n".join(lines) + "\n"

    def update_from_api(self, workflow_id: str, name: str | None = None) -> None:
        """
        Update metadata from API response.

        Args:
            workflow_id: The workflow ID from the API.
            name: Optional workflow name from the API.
        """
        self.workflow_id = workflow_id
        if name:
            self.name = name
        now = dt.datetime.now(dt.timezone.utc).isoformat()
        if not self.creation_date:
            self.creation_date = now
        self.last_update_date = now


def get_git_author(file_path: Path | None = None) -> str | None:
    """
    Get git author information for the current repository.

    Args:
        file_path: Optional path to a file in the git repository.

    Returns:
        Author string in format "Name <email>" or None if not available.
    """
    try:
        # Try to get author from git config
        result = subprocess.run(
            ["git", "config", "user.name"],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
        name = result.stdout.strip()

        result = subprocess.run(
            ["git", "config", "user.email"],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
        email = result.stdout.strip()

        if name and email:
            return f"{name} <{email}>"
        elif name:
            return name
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Fallback: try to get from git log if file_path is provided
    if file_path:
        try:
            result = subprocess.run(
                ["git", "log", "-1", "--format=%an <%ae>", "--", str(file_path)],
                capture_output=True,
                text=True,
                check=True,
                timeout=5,
            )
            author = result.stdout.strip()
            if author:
                return author
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            pass

    return None


def insert_metadata_block(content: str, metadata: WorkflowMetadata) -> str:
    """
    Insert or update metadata block in file content.

    Args:
        content: The file content.
        metadata: The metadata to insert.

    Returns:
        The content with metadata block inserted/updated.
    """
    metadata_block = metadata.to_block()

    # Check if metadata block already exists
    existing_metadata = WorkflowMetadata.from_string(content)
    if existing_metadata:
        # Replace existing metadata block
        pattern = r"#!/notte/workflow\s*\n(?:#\s*\n)?(?:#\s*(.+?)\s*\n)*"
        content = re.sub(pattern, metadata_block + "\n", content, flags=re.MULTILINE)
    else:
        # Insert metadata block at the beginning
        # If there's a shebang, insert after it, otherwise at the start
        shebang_pattern = r"^#![^\n]+\n"
        shebang_match = re.match(shebang_pattern, content)

        if shebang_match:
            # Insert after shebang
            shebang = shebang_match.group(0)
            rest = content[len(shebang) :]
            content = shebang + metadata_block + "\n" + rest
        else:
            # Insert at the beginning
            content = metadata_block + "\n" + content

    return content


def comment_main_block(content: str) -> tuple[str, bool]:
    """
    Comment out the `if __name__ == "__main__"` block.

    Args:
        content: The file content.

    Returns:
        Tuple of (modified content, whether block was found and commented).
    """
    lines = content.split("\n")
    main_start = None

    # Find the line with `if __name__ == "__main__":`
    for i, line in enumerate(lines):
        if re.match(r'^\s*if\s+__name__\s*==\s*["\']__main__["\']\s*:', line):
            main_start = i
            break

    if main_start is None:
        return content, False

    # Find the end of the block (all indented lines after the if statement)
    main_end = main_start + 1
    if main_start < len(lines):
        # Get the indentation level of the if statement itself
        if_line = lines[main_start]
        if_indent = len(if_line) - len(if_line.lstrip())

        # Find all subsequent lines that are indented more than the if statement
        # (i.e., the body of the if block)
        for i in range(main_start + 1, len(lines)):
            line = lines[i]
            if not line.strip():  # Empty line, include it
                main_end = i + 1
                continue
            line_indent = len(line) - len(line.lstrip())
            # Include lines that are indented more than the if statement
            if line_indent > if_indent:
                main_end = i + 1
            else:
                # Hit a line at same or less indentation - end of block
                break

    # Comment out all lines in the block
    new_lines = lines.copy()
    for i in range(main_start, main_end):
        if new_lines[i].strip():  # Only comment non-empty lines
            new_lines[i] = "# " + new_lines[i]

    return "\n".join(new_lines), True


def uncomment_main_block(content: str) -> tuple[str, bool]:
    """
    Uncomment the `if __name__ == "__main__"` block.

    Args:
        content: The file content.

    Returns:
        Tuple of (modified content, whether block was found and uncommented).
    """
    lines = content.split("\n")
    main_start = None

    # Find the commented line with `if __name__ == "__main__":`
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("#") and re.match(r'#\s*if\s+__name__\s*==\s*["\']__main__["\']\s*:', stripped):
            main_start = i
            break

    if main_start is None:
        return content, False

    # Find the end of the commented block
    main_end = main_start + 1
    if main_start < len(lines):
        # Get the indentation level of the commented if statement
        commented_if_line = lines[main_start]
        # Uncomment temporarily to get original indentation
        uncommented_if = commented_if_line.lstrip("# ").lstrip("#")
        if_indent = len(uncommented_if) - len(uncommented_if.lstrip())

        # Find all subsequent commented lines that are indented more than the if statement
        for i in range(main_start + 1, len(lines)):
            line = lines[i]
            if not line.strip():  # Empty line, include it
                main_end = i + 1
                continue
            if line.strip().startswith("#"):
                # Uncomment temporarily to check indentation
                uncommented = line.lstrip("# ").lstrip("#")
                if uncommented.strip():
                    uncommented_indent = len(uncommented) - len(uncommented.lstrip())
                    if uncommented_indent > if_indent:
                        main_end = i + 1
                    else:
                        break
                else:
                    main_end = i + 1
            else:
                # Hit a non-commented line - end of block
                break

    # Uncomment all lines in the block
    new_lines = lines.copy()
    for i in range(main_start, main_end):
        if new_lines[i].strip().startswith("#"):
            # Remove leading "# " or "#"
            if new_lines[i].startswith("# "):
                new_lines[i] = new_lines[i][2:]
            elif new_lines[i].startswith("#"):
                new_lines[i] = new_lines[i][1:]

    return "\n".join(new_lines), True
