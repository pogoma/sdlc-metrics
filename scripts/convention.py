# python-file: module
"""The shared libraries of the Python convention, seen from the metrics.

Schemas and measurements are YAML, and a measurement is checked against its
schema by the JSON Schema validator of the Python convention (SDLC-0042). The
metrics repository has no copy of either: it is mounted as metrics/ next to
docs/conventions/python in a developer repository, and takes the libraries
from there.

The shared code of the convention sits in a package called libs, a name a
caller may already use for its own package, so it is loaded from its own
directory under a name of its own. A caller that has the libraries already —
the process does — hands the validator over instead.

Standard library only. Identifiers, docstrings and comments are English; text
printed for the owner is Polish (SDLC-0001).
"""

import importlib
import importlib.util
import sys
import threading
from pathlib import Path
from typing import Optional

MODULE_NAME = "metrics_convention_libs"
RELATIVE = Path("docs") / "conventions" / "python" / "scripts" / "libs"
MISSING = ("konwencja Pythona nie jest podłączona w {} repozytorium developerskiego, "
           "a pomiary czyta i sprawdza jej biblioteka".format(RELATIVE.as_posix()))

LOCK = threading.Lock()
LOADED = None


class MissingLibrary(RuntimeError):
    """The convention is not mounted next to the metrics."""


def package_path(start: Optional[Path] = None) -> Optional[Path]:
    """Directory of the shared libraries, found by walking up from this module."""
    here = (start or Path(__file__)).resolve()
    for parent in here.parents:
        candidate = parent / RELATIVE
        if (candidate / "yaml").is_dir() and (candidate / "json_schema").is_dir():
            return candidate
    return None


def validator():
    """The JSON Schema validator of the convention, imported once."""
    global LOADED
    if LOADED is not None:
        return LOADED
    with LOCK:
        if LOADED is not None:
            return LOADED
        found = package_path()
        if found is None:
            raise MissingLibrary(MISSING)
        spec = importlib.util.spec_from_file_location(
            MODULE_NAME, found / "__init__.py",
            submodule_search_locations=[str(found)])
        if spec is None or spec.loader is None:
            raise MissingLibrary(MISSING)
        module = importlib.util.module_from_spec(spec)
        # The packages import their own submodules by this name.
        sys.modules[MODULE_NAME] = module
        try:
            spec.loader.exec_module(module)
            loaded = importlib.import_module(MODULE_NAME + ".json_schema")
        except Exception:
            for name in [name for name in sys.modules
                         if name == MODULE_NAME or name.startswith(MODULE_NAME + ".")]:
                del sys.modules[name]
            raise
        LOADED = loaded
        return loaded


def yaml():
    """The YAML library of the convention, loaded with the validator."""
    validator()
    return importlib.import_module(MODULE_NAME + ".yaml")
