import io
import re
import requests
from typing import Dict, Tuple, Optional
from loguru import logger

try:
    import PyPDF2
    from PIL import Image
    import pytesseract
    PYPDF_AVAILABLE = True
except ImportError:
    PYPDF_AVAILABLE = False
    logger.warning("PyPDF2, PIL, or pytesseract not installed. PDF processing will be limited.")

class PDFHandler:
    """Handles PDF extraction for academic papers, with special handling for ArXiv."""
    
    @staticmethod
    def extract_arxiv_id_from_url(url: str) -> Optional[str]:
        """Extract ArXiv ID from a URL."""
        patterns = [
            r'arxiv\.org/abs/(\d+\.\d+)',
            r'arxiv\.org/pdf/(\d+\.\d+)',
            r'arxiv\.org/e-print/(\d+\.\d+)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None
    
    @staticmethod
    def get_pdf_url_from_arxiv_id(arxiv_id: str) -> str:
        """Convert ArXiv ID to direct PDF URL."""
        return f"https://arxiv.org/pdf/{arxiv_id}.pdf"
    
    @staticmethod
    def download_pdf(url: str) -> Optional[bytes]:
        """Download PDF content from URL."""
        try:
            response = requests.get(url, stream=True, timeout=30)
            response.raise_for_status()
            return response.content
        except Exception as e:
            logger.error(f"Failed to download PDF: {e}")
            return None
    
    @staticmethod
    def count_figures_and_tables(pdf_content: bytes) -> Tuple[int, int]:
        """Count figures and tables in a PDF document."""
        if not PYPDF_AVAILABLE:
            logger.error("PyPDF2 not available for PDF processing")
            return (0, 0)
        
        try:
            pdf_reader = PyPDF2.PdfReader(io.BytesIO(pdf_content))
            text = ""
            for page in pdf_reader.pages:
                text += page.extract_text() or ""
            
            # Look for explicit figure/table references in the text
            figure_pattern = r'(?:Figure|Fig\.)\s+\d+'
            table_pattern = r'Table\s+\d+'
            
            figures = set(re.findall(figure_pattern, text, re.IGNORECASE))
            tables = set(re.findall(table_pattern, text, re.IGNORECASE))
            
            return (len(figures), len(tables))
        except Exception as e:
            logger.error(f"Error processing PDF: {e}")
            return (0, 0)
    
    @staticmethod
    def process_arxiv_paper(url: str) -> Dict[str, int]:
        """Process ArXiv paper to extract figures and tables count."""
        arxiv_id = PDFHandler.extract_arxiv_id_from_url(url)
        if not arxiv_id:
            # If we're on the main page, we need to search for the paper
            logger.info("No ArXiv ID found in URL, need to search for paper")
            return {"figures": 0, "tables": 0}
        
        pdf_url = PDFHandler.get_pdf_url_from_arxiv_id(arxiv_id)
        pdf_content = PDFHandler.download_pdf(pdf_url)
        
        if not pdf_content:
            return {"figures": 0, "tables": 0}
        
        figures, tables = PDFHandler.count_figures_and_tables(pdf_content)
        return {"figures": figures, "tables": tables}