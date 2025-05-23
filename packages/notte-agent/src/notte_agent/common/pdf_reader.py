from abc import ABC, abstractmethod

from notte_core.data.space import DataSpace


class BasePDFReader(ABC):
    @abstractmethod
    async def read_pdf(self, url: str) -> DataSpace:
        """Reads a PDF file and returns its content as markdown."""
        pass

    @classmethod
    def instructions(cls) -> str:
        return """PDF READING INSTRUCTION
==========================

When encountering PDF documents:
- Do not use the "scrape" action.
- PDF OCR (Optical Character Recognition) is automatically enabled for these documents.

"""
