from enum import Enum
from typing import Annotated, Any, Generic, Self, TypeVar, cast

import requests
from pydantic import BaseModel, Field, RootModel, model_serializer, model_validator

from notte_core.errors.processing import InvalidInternalCheckError, ScrapeFailedError

TBaseModel = TypeVar("TBaseModel", bound=BaseModel, covariant=True)
# Legacy name: used as the raw structured-data wrapper before validating
# against a user-provided schema, so it must preserve any JSON root shape.
DictBaseModel = RootModel[Any]


class NoStructuredData(BaseModel):
    """Placeholder model for when no structured data is present."""

    pass


class ImageCategory(Enum):
    """Category of the image."""

    FAVICON = "favicon"
    ICON = "icon"
    CONTENT_IMAGE = "content_image"
    DECORATIVE = "decorative"
    SVG_ICON = "svg_icon"
    SVG_CONTENT = "svg_content"


class ImageData(BaseModel):
    url: Annotated[str | None, Field(description="URL of the image")] = None
    category: Annotated[ImageCategory | None, Field(description="Category of the image (icon, svg, content, etc.)")] = (
        None
    )
    description: Annotated[str | None, Field(description="Description of the image")] = None

    def bytes(self) -> bytes:
        if self.url is None:
            raise InvalidInternalCheckError(
                check="image URL is not available. Cannot retrieve image bytes.",
                url=self.url,
                dev_advice=(
                    "Check the `ImageData` construction process in the `DataScraping` pipeline to diagnose this issue."
                ),
            )
        return requests.get(self.url).content


class StructuredData(BaseModel, Generic[TBaseModel]):
    success: Annotated[bool, Field(description="Whether the data was extracted successfully")] = True
    error: Annotated[str | None, Field(description="Error message if the data was not extracted successfully")] = None
    data: Annotated[
        TBaseModel | DictBaseModel | None, Field(description="Structured data extracted from the page in JSON format")
    ] = None

    @model_validator(mode="before")
    def wrap_dict_in_root_model(cls, values: dict[str, Any]) -> dict[str, Any]:
        if isinstance(values, dict) and "data" in values and isinstance(values["data"], (dict, list)):  # type: ignore[arg-type]
            values["data"] = DictBaseModel(values["data"])
        # if error and is not empty, set success to False
        error = values.get("error")
        if error is not None and len(error.strip()) > 0:
            values["success"] = False
        return values

    @model_validator(mode="after")
    def ensure_data_if_success(self) -> Self:
        if self.success and self.data is None:
            raise ValueError("Scraping was successful but data field is None")
        return self

    @model_validator(mode="after")
    def ensure_no_error_success(self) -> Self:
        if self.success and (self.error is not None and self.error != ""):
            raise ValueError("If error, make sure success is False. If success, make sure error is null.")
        return self

    @model_serializer
    def serialize_model(self):
        result: dict[str, Any] = {
            "success": self.success,
            "error": self.error,
        }
        if isinstance(self.data, RootModel):
            result["data"] = self.data.root  # type: ignore[attr-defined]
        elif isinstance(self.data, BaseModel):
            result["data"] = self.data.model_dump()
        else:
            result["data"] = self.data
        return result

    def _schema(self) -> type[BaseModel] | None:
        """The model `data` should be validated against, when it is known.

        `StructuredData[Profile]` records `Profile` in pydantic's generic metadata, so a
        raw JSON payload can be validated back into it. Returns None for the
        unparametrized form and for `StructuredData[BaseModel]`, where no schema was
        provided and there is therefore nothing to validate against.
        """
        args: tuple[Any, ...] = type(self).__pydantic_generic_metadata__["args"]
        if len(args) != 1:
            return None
        schema = args[0]
        if not isinstance(schema, type) or not issubclass(schema, BaseModel) or schema is BaseModel:
            return None
        return schema

    def get(self) -> TBaseModel:
        """Get the extracted data, raising ScrapeFailedError if extraction failed.

        A payload that came in as raw JSON is stored wrapped in a `DictBaseModel`
        (`RootModel[Any]`) by `wrap_dict_in_root_model`. It is validated back into the
        schema this `StructuredData` was parametrized with, so the returned value is
        always a model. When no schema is known the `RootModel` wrapper is itself the
        model, and the raw payload stays reachable through `.root` / `model_dump()`.

        Raises:
            ScrapeFailedError: if the extraction failed or produced no data.
            ValidationError: if the payload does not match the parametrized schema.
        """
        if not self.success or self.data is None:
            raise ScrapeFailedError(self.error or "Unknown extraction error")
        data: TBaseModel | DictBaseModel = self.data
        if isinstance(data, RootModel):
            # local alias: keeps the payload typed as `Any` instead of `RootModel[Unknown]`
            wrapper = cast(DictBaseModel, data)
            schema = self._schema()
            if schema is None:
                # no schema was provided: the RootModel wrapper is itself the model
                return cast(TBaseModel, wrapper)
            return cast(TBaseModel, schema.model_validate(wrapper.root))
        return data


class DataSpace(BaseModel):
    markdown: Annotated[str, Field(description="Markdown representation of the extracted data")]
    images: Annotated[
        list[ImageData] | None, Field(description="List of images extracted from the page (ID and download link)")
    ] = None
    structured: Annotated[
        StructuredData[BaseModel] | None, Field(description="Structured data extracted from the page in JSON format")
    ] = None

    @staticmethod
    def from_structured(data: BaseModel) -> "DataSpace":
        return DataSpace(
            markdown="No markdown available",
            structured=StructuredData(
                success=True,
                data=data,
                error=None,
            ),
        )

    @property
    def structured_scrape_failed(self) -> bool:
        return self.structured is not None and not self.structured.success

    @property
    def structured_scrape_exception(self) -> Exception | None:
        if not self.structured_scrape_failed:
            return None
        error_msg = (self.structured.error if self.structured is not None else None) or "Unknown extraction error"
        return ScrapeFailedError(error_msg)
