import threading
from collections import deque
from dataclasses import dataclass
from typing import final

from notte.utils.singleton import Singleton


@dataclass(frozen=True)
class PortRange:
    start: int
    end: int


@final
class PortManager(metaclass=Singleton):
    def reset(self, start: int, nb: int) -> None:
        if nb <= 0:
            raise ValueError("Number of ports must be greater than 0")
        if start < 0:
            raise ValueError("Start port must be greater than 0")
        port_range = PortRange(start, start + nb - 1)
        if self.port_range is not None and self.port_range != port_range:
            raise ValueError("Port range already set. PortManager is already initialized.")
        self.port_range = port_range
        self._available_ports = deque(range(self.port_range.start, self.port_range.end + 1))

    def __init__(self) -> None:
        """Initialize the port manager with a range of ports.

        Args:
            port_range: The range of ports to manage (inclusive start, inclusive end)
        """
        self._used_ports: set[int] = set()
        self._available_ports: deque[int] = deque()
        self._lock: threading.Lock = threading.Lock()
        self.port_range: PortRange | None = None

    def acquire_port(self) -> int | None:
        """Get next available port from the pool.

        Returns:
            An available port number or None if no ports are available
        """
        if self.port_range is None:
            raise ValueError("PortManager is not initialized. Call reset() first.")
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
        if self.port_range is None:
            raise ValueError("PortManager is not initialized. Call reset() first.")
        if not (self.port_range.start <= port <= self.port_range.end):
            raise ValueError(f"Port {port} is outside valid range {self.port_range}")

        if port not in self._used_ports:
            raise ValueError(f"Port {port} is not currently in use")

        self._used_ports.remove(port)
        self._available_ports.append(port)

    def is_initialized(self) -> bool:
        return self.port_range is not None

    @property
    def available_ports(self) -> list[int]:
        """Get list of currently available ports."""
        return list(self._available_ports)

    @property
    def used_ports(self) -> list[int]:
        """Get list of currently used ports."""
        return list(self._used_ports)

    def is_port_available(self, port: int) -> bool:
        """Check if a specific port is available.

        Args:
            port: The port number to check

        Returns:
            True if the port is available, False otherwise
        """
        return port in self._available_ports


def get_port_manager() -> PortManager | None:
    manager = PortManager()
    if not manager.is_initialized():
        return None
    return manager
