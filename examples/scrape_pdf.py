import asyncio

from notte_integrations.pdf.docling import DoclingPDFReader

import notte

if __name__ == "__main__":

    async def scrape_pdf(target_url: str):
        async with notte.Session(pdf_reader=DoclingPDFReader()) as session:
            data = await session.scrape(url=target_url)
            return data

    print(asyncio.run(scrape_pdf(target_url="https://arxiv.org/pdf/cs/0302013.pdf")))
