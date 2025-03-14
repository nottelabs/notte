import threading
from collections import deque
from dataclasses import dataclass
from typing import Final, final


@dataclass(frozen=True)
class PortRange:
    start: int
    end: int


@final
class PortManager:
    def __init__(self, start: int, nb: int) -> None:
        """Initialize the port manager with a range of ports.

        Args:
            port_range: The range of ports to manage (inclusive start, inclusive end)
        """
        if nb <= 0:
            raise ValueError("Number of ports must be greater than 0")
        if start < 0:
            raise ValueError("Start port must be greater than 0")
        self.port_range: Final[PortRange] = PortRange(start, start + nb - 1)
        self._used_ports: set[int] = set()
        self._available_ports: deque[int] = deque(range(self.port_range.start, self.port_range.end + 1))
        self._lock = threading.Lock()

    def acquire_port(self) -> int | None:
        """Get next available port from the pool.

        Returns:
            An available port number or None if no ports are available
        """
        with self._lock:
            if not self._available_ports:
                return None

            port = self._available_ports.popleft()
            self._used_ports.add(port)
            return port

    def release_port(self, port: int) -> None:
        """Release a port back to the pool.

        Args:
            port: The port number to release

        Raises:
            ValueError: If the port is not in use or outside the valid range
        """
        with self._lock:
            if not (self.port_range.start <= port <= self.port_range.end):
                raise ValueError(f"Port {port} is outside valid range {self.port_range}")

            if port not in self._used_ports:
                raise ValueError(f"Port {port} is not currently in use")

            self._used_ports.remove(port)
            self._available_ports.append(port)

    @property
    def available_ports(self) -> list[int]:
        """Get list of currently available ports."""
        with self._lock:
            return list(self._available_ports)

    @property
    def used_ports(self) -> list[int]:
        """Get list of currently used ports."""
        with self._lock:
            return list(self._used_ports)

    def is_port_available(self, port: int) -> bool:
        """Check if a specific port is available.

        Args:
            port: The port number to check

        Returns:
            True if the port is available, False otherwise
        """
        with self._lock:
            return port in self._available_ports
