from abc import ABC, abstractmethod

from notte_core.data.space import DataSpace


class BasePDFReader(ABC):
    @abstractmethod
    async def read_pdf(self, url: str) -> DataSpace:
        """Reads a PDF file and returns its content as markdown."""
        pass
