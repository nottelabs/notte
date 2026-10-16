# @sniptest filename=notte_mongodb.py
# @sniptest typecheck_only=true
import os
from typing import Any

from notte_sdk import NotteClient
from pymongo import MongoClient
from pymongo.errors import OperationFailure

url = "https://example.com"
with NotteClient().Session(max_duration_minutes=3) as session:
    try:
        with MongoClient[dict[str, Any]](os.environ["MONGODB_URI"], timeoutMS=10_000) as mongo:
            collection = mongo[os.environ.get("MONGODB_DATABASE", "notte")][
                os.environ.get("MONGODB_COLLECTION", "pages")
            ]
            session.execute(type="goto", url=url)
            inserted = collection.insert_one(
                {"url": url, "markdown": session.scrape(), "session_id": session.session_id}
            )
            result = {"document_id": str(inserted.inserted_id), "session_id": session.session_id}
            print(result["document_id"])
    except Exception as error:
        code = error.code if isinstance(error, OperationFailure) else None
        raise RuntimeError(f"MongoDB export failed (session {session.session_id}, code {code})") from None
