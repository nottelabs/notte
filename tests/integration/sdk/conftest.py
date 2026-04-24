import os

import pytest
from dotenv import load_dotenv
from notte_sdk import NotteClient

# Persona IDs that must NOT be deleted (used by other test suites / frontend).
IMPORTANT_PERSONAS = {
    # Front end tests
    "f2e2834b-a054-4a96-a388-a447c37756ff",
    "131a21e1-8c8e-4016-80b9-765c0ce4fb5c",
    "ee3da1f5-e53c-4159-839d-e8db16bbe2e7",
    "46d0649e-1d13-47be-a21f-703ce4cf02ea",
    # Monorepo
    "7abb4f37-25a1-4409-98d9-c4c916918254",
    "0a0a0a0a-4444-5555-6666-777777777701",
    "0a0a0a0a-4444-5555-6666-777777777702",
    # Others
    "23ae78af-93b4-4aeb-ba21-d18e1496bdd9",
    "4e9faffa-ae3e-4a86-a87f-584bf77794e0",
}


@pytest.fixture(scope="session", autouse=True)
def cleanup_all_personas():
    """Delete all non-important active personas before and after the test session.

    Setup: prevents accumulated leaked personas from previous (possibly crashed)
    CI runs from exhausting the staging account's 10-persona limit.
    Teardown: cleans up personas leaked by the current run so overlapping or
    subsequent runs don't hit the cap.
    """
    _ = load_dotenv()
    api_key = os.getenv("NOTTE_API_KEY")
    if not api_key:
        # Nothing we can do without credentials — let the actual tests fail
        # with a clear auth error instead of masking it here.
        yield
        return

    client = NotteClient(api_key=api_key)

    def _delete_non_important_personas(phase: str) -> None:
        try:
            for persona in client.personas.list(page_size=100):
                if persona.persona_id not in IMPORTANT_PERSONAS:
                    try:
                        client.personas.delete(persona.persona_id)
                    except Exception as e:
                        print(f"[cleanup_all_personas] {phase}: failed to delete {persona.persona_id}: {e}")
        except Exception as e:
            print(f"[cleanup_all_personas] {phase}: persona listing failed, skipping cleanup: {e}")

    _delete_non_important_personas("setup")
    yield
    _delete_non_important_personas("teardown")
