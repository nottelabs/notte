from docling.document_converter import DocumentConverter
from notte_agent.common.pdf_reader import BasePDFReader
from notte_core.data.space import DataSpace
from typing_extensions import override


class DoclingPDFReader(BasePDFReader):
    @override
    async def read_pdf(self, url: str) -> DataSpace:
        """Reads a PDF file and returns its content as markdown."""
        converter = DocumentConverter()
        result = converter.convert(source=url)
        return DataSpace(markdown=result.document.export_to_markdown())
