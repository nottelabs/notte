import pytest
import requests


@pytest.mark.skip(reason="Run this manually when you want to update the spec")
def test_openapi_spec_should_identical_on_staging_and_prod():
    "Compare spec on staging and production"
    staging_spec = requests.get("https://staging.notte.cc/openapi.json")
    production_spec = requests.get("https://api.notte.cc/openapi.json")
    assert staging_spec.json() == production_spec.json(), "Staging and production specs are not identical"
