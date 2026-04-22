"""image_generate tool — re-exports TOOL + provider registry."""

from .image_generate import DESCRIPTION, NAME, SPEC, _tool_check_fn, execute
from .registry import GeneratedImage, ImageGenerateProvider, registry

TOOL = {
    "spec": SPEC,
    "execute": execute,
    "check_fn": _tool_check_fn,
    "max_result_size_chars": 4_000,
}

__all__ = [
    "NAME",
    "SPEC",
    "TOOL",
    "execute",
    "DESCRIPTION",
    "GeneratedImage",
    "ImageGenerateProvider",
    "registry",
]
