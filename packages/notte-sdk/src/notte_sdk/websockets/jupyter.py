from typing import Any


def display_image_in_notebook(image_data: bytes) -> Any:
    try:
        from IPython.display import (
            clear_output,
            display,  # pyright: ignore [reportUnknownVariableType]
        )
        from notte_core.utils.image import image_from_bytes

        image = image_from_bytes(image_data)
        clear_output(wait=True)
        return display(image)
    except ImportError as e:
        raise RuntimeError("This method requires IPython/Jupyter environment") from e
