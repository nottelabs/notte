from importlib.metadata import requires

from packaging.requirements import Requirement


def _requirement(package: str, name: str) -> Requirement:
    for spec in requires(package) or []:
        requirement = Requirement(spec)
        if requirement.name == name and requirement.marker is None:
            return requirement
    raise AssertionError(f"{package} does not require {name}")


def test_notte_core_aiohttp_range():
    specifier = _requirement("notte-core", "aiohttp").specifier
    # 3.11.13 is the aiohttp bundled with Pyodide 0.29, where the SDK also runs.
    assert specifier.contains("3.11.13")
    # Newer 3.x releases must stay installable next to libraries that require them.
    assert specifier.contains("3.14.3")
    assert not specifier.contains("4.0.0")
