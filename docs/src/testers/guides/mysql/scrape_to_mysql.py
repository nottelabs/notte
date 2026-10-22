# @sniptest filename=scrape_to_mysql.py
import os
import ssl

import pymysql
from scrape_function import PageData, scrape_page


def save_page(url: str, page: PageData) -> None:
    connection = pymysql.connect(
        host=os.environ["MYSQL_HOST"],
        port=int(os.environ.get("MYSQL_PORT", "3306")),
        user=os.environ["MYSQL_USER"],
        password=os.environ["MYSQL_PASSWORD"],
        database=os.environ["MYSQL_DATABASE"],
        ssl=ssl.create_default_context(cafile=os.environ.get("MYSQL_SSL_CA")),
        charset="utf8mb4",
        connect_timeout=10,
        read_timeout=30,
        write_timeout=30,
        autocommit=False,
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO scraped_pages (url, title, description, scraped_at) "
                "VALUES (%s, %s, %s, UTC_TIMESTAMP()) "
                "ON DUPLICATE KEY UPDATE title=%s, description=%s, scraped_at=UTC_TIMESTAMP()",
                (url, page.title, page.description, page.title, page.description),
            )
        connection.commit()
    finally:
        connection.close()


def run(url: str) -> dict:
    page = scrape_page(url)
    save_page(url, page)
    return {"url": url, "saved": True}


if __name__ == "__main__":
    print(run("https://example.com"))
