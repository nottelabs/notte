"""Preserve the existing upload reference field types and integrity-check path."""

from notte_sdk._generated import models


class UploadReference(models.RunPayloadReference):
    upload_id: str  # pyright: ignore[reportIncompatibleVariableOverride]


class UploadResponse(models.RunPayloadUploadResponse):
    reference: UploadReference  # pyright: ignore[reportIncompatibleVariableOverride]
