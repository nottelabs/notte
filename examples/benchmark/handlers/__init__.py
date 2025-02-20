import importlib
import pathlib
import pkgutil


def autodiscover():
    """
    Automatically import all modules in this package to trigger the decorators
    """
    # Get the path of the handlers subpackage
    package_path = pathlib.Path(__file__).parent

    # Import all .py files in the package
    for module_info in pkgutil.iter_modules([str(package_path)]):
        if module_info.name != "__init__":
            _ = importlib.import_module(f"{__package__}.{module_info.name}")


autodiscover()
