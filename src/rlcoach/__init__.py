"""rlcoach: All-local Rocket League replay analysis tool for coaching."""

import importlib

from .version import get_package_version

__version__ = get_package_version()
__description__ = "All-local Rocket League replay analysis tool for coaching"


def __getattr__(name: str):
    """Lazily expose optional top-level subpackages."""
    if name == "api":
        return importlib.import_module("rlcoach.api")
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
