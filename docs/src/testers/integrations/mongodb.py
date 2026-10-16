# @sniptest filename=notte_mongodb.py
# @sniptest typecheck_only=true
import os
from typing import Any

from notte_sdk import NotteClient
from pymongo import MongoClient
from pymongo.errors import OperationFailure

url = "https://example.com"
uri = os.environ.get("MONGODB_URI")
if not uri:
    raise ValueError("Set MONGODB_URI before running this example")

with NotteClient().Session(max_duration_minutes=3) as session:
    stage = "MongoDB connection"
    try:
        with MongoClient[dict[str, Any]](uri, timeoutMS=10_000, serverSelectionTimeoutMS=10_000) as mongo:
            mongo.admin.command("ping")
            collection = mongo[os.environ.get("MONGODB_DATABASE", "notte")][
                os.environ.get("MONGODB_COLLECTION", "pages")
            ]
            stage = "browser navigation"
            session.execute(type="goto", url=url)
            stage = "browser scrape"
            markdown = session.scrape()
            stage = "MongoDB insert"
            inserted = collection.insert_one({"url": url, "markdown": markdown, "session_id": session.session_id})
            result = {"document_id": str(inserted.inserted_id), "session_id": session.session_id}
            print(result["document_id"])
    except Exception as error:
        code = error.code if isinstance(error, OperationFailure) else None
        raise RuntimeError(
            f"MongoDB export failed (session {session.session_id}, code {code}): {stage}: {type(error).__name__}"
        ) from None
