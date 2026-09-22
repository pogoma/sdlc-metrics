# python-file: module
"""Kinds and versions of measurements and their schemas (SDLC-0013, SDLC-0030).

A schema lives in schemas/<kind>/<version>.yaml of this repository and is the
only description of what a measurement of that kind and version looks like.
It is JSON Schema 2020-12 written in YAML, and the validator of the Python
convention applies it (SDLC-0042); this module only finds the right schema,
tells the kind and the version of a measurement and turns the problems into
Polish sentences.

Standard library only. Identifiers, docstrings and comments are English; text
printed for the owner is Polish (SDLC-0001).
"""

import re
from pathlib import Path
from typing import Dict, List, Optional

import convention

SCHEMAS_DIRECTORY = "schemas"
RAW_DIRECTORY = "raw"
LEGACY_DIRECTORY = "legacy"
VERSION_FIELD = "schema_version"
KIND_FIELD = "kind"
# Measurements of protocol runs predate the kind field, so a file without it
# is one of theirs; the directory says the same thing for the ones already
# stored (SDLC-0030).
PROCESS_KIND = "process"
PERFORMANCE_KIND = "performance"
SCHEMA_SUFFIX = ".yaml"
JSON_SUFFIX = ".json"
YAML_SUFFIX = ".yaml"
# First version of each kind stored as a YAML file (SDLC-0042); the versions
# before it stay JSON until a migration carries them over.
YAML_SINCE = {PROCESS_KIND: 3, PERFORMANCE_KIND: 2}
VERSION_NAME = re.compile(r"^(\d+)\.yaml$")
KIND_NAME = re.compile(r"^[a-z][a-z0-9-]*$")


def repository_root(module: Path) -> Path:
    """Root of the metrics repository, taken from the module location."""
    return module.resolve().parents[1]


def schemas_root(root: Optional[Path] = None) -> Path:
    """Directory holding one directory per kind of measurement."""
    base = root if root is not None else repository_root(Path(__file__))
    return base / SCHEMAS_DIRECTORY


def directory(kind: str = PROCESS_KIND, root: Optional[Path] = None) -> Path:
    """Directory holding one schema file per version of one kind."""
    return schemas_root(root) / kind


def kinds(root: Optional[Path] = None) -> List[str]:
    """Kinds that have a directory of schemas, in alphabetical order."""
    place = schemas_root(root)
    if not place.is_dir():
        return []
    return sorted(path.name for path in place.iterdir()
                  if path.is_dir() and KIND_NAME.match(path.name))


def measurements_directory(kind: str = PROCESS_KIND,
                           root: Optional[Path] = None) -> Path:
    """Directory holding the stored measurements of one kind."""
    base = root if root is not None else repository_root(Path(__file__))
    return base / RAW_DIRECTORY / kind


def versions(kind: str = PROCESS_KIND, root: Optional[Path] = None) -> List[int]:
    """Versions of one kind that have a schema, in ascending order."""
    found = []
    place = directory(kind, root)
    if not place.is_dir():
        return found
    for path in sorted(place.iterdir()):
        match = VERSION_NAME.match(path.name)
        if match:
            found.append(int(match.group(1)))
    return sorted(found)


def latest(kind: str = PROCESS_KIND, root: Optional[Path] = None) -> int:
    """Newest version of one kind that has a schema."""
    found = versions(kind, root)
    if not found:
        raise ValueError(
            "rodzaj {}: brak katalogu schematów albo żadnego schematu wersji".format(kind))
    return found[-1]


def schema_path(kind: str, version: int, root: Optional[Path] = None) -> Path:
    """File of the schema of one kind and version."""
    return directory(kind, root) / "{}{}".format(version, SCHEMA_SUFFIX)


def load(kind: str, version: int,
         root: Optional[Path] = None) -> Dict[str, object]:
    """Schema of one kind and version, as a document."""
    path = schema_path(kind, version, root)
    if not path.is_file():
        raise ValueError("brak schematu rodzaju {} w wersji {}".format(kind, version))
    library = convention.validator()
    try:
        document = library.load(path)
    except library.LoadError as error:
        raise ValueError("schemat rodzaju {} w wersji {}: {}".format(
            kind, version, error)) from error
    if not isinstance(document, dict):
        raise ValueError("schemat rodzaju {} w wersji {} nie jest obiektem".format(
            kind, version))
    return document


def version_of(document: object, path: Optional[Path] = None) -> int:
    """Version a measurement declares, or the one its directory implies.

    Version 1 and version 0 predate the field, so the directory tells them
    apart: a file in legacy/ is version 0, anything else is version 1.
    """
    if isinstance(document, dict) and VERSION_FIELD in document:
        value = document[VERSION_FIELD]
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("{} nie jest liczbą całkowitą".format(VERSION_FIELD))
        return value
    if path is not None and LEGACY_DIRECTORY in path.resolve().parts:
        return 0
    return 1


def kind_of(document: object, path: Optional[Path] = None,
            root: Optional[Path] = None) -> str:
    """Kind a measurement declares, or the one its directory implies.

    Measurements of protocol runs predate the field, so a file without it is
    one of theirs; a file stored under raw/<kind>/ says the same thing through
    its directory (SDLC-0030). A declared kind without a directory of schemas
    is a refusal, not a silent pass.
    """
    declared = None
    if isinstance(document, dict) and KIND_FIELD in document:
        value = document[KIND_FIELD]
        if not isinstance(value, str) or not KIND_NAME.match(value):
            raise ValueError("{} nie jest nazwą rodzaju".format(KIND_FIELD))
        declared = value
    if declared is None:
        declared = directory_kind(path) or PROCESS_KIND
    known = kinds(root)
    if known and declared not in known:
        raise ValueError("nieznany rodzaj pomiaru {}".format(declared))
    return declared


def directory_kind(path: Optional[Path]) -> Optional[str]:
    """Kind read from the raw/<kind>/ directory a measurement lies in."""
    if path is None:
        return None
    parts = path.resolve().parts
    if RAW_DIRECTORY not in parts:
        return None
    place = parts.index(RAW_DIRECTORY)
    if place + 2 >= len(parts):
        return None
    name = parts[place + 1]
    return name if KIND_NAME.match(name) else None


def suffix_for(kind: str, version: int) -> str:
    """Extension of a measurement file of one kind and version (SDLC-0042)."""
    since = YAML_SINCE.get(kind)
    return YAML_SUFFIX if since is not None and version >= since else JSON_SUFFIX


def read(path: Path) -> object:
    """Content of a measurement file, JSON or YAML by its extension.

    Raises ValueError with a Polish sentence when the file cannot be read.
    """
    library = convention.validator()
    try:
        return library.load(path)
    except library.LoadError as error:
        raise ValueError(str(error)) from error


def validate(document: object, version: int, root: Optional[Path] = None,
             kind: str = PROCESS_KIND, validator=None) -> List[str]:
    """Everything wrong with one measurement, as a list of Polish sentences.

    A caller that has the validator of the convention loaded already hands it
    over; otherwise it is loaded here.
    """
    schema = load(kind, version, root)
    library = validator if validator is not None else convention.validator()
    try:
        problems = library.validate(document, schema)
    except library.SchemaError as error:
        raise ValueError("schemat rodzaju {} w wersji {} jest błędny: {}".format(
            kind, version, error)) from error
    return ["pomiar{}: {}".format(problem.instance_path, problem.message)
            for problem in problems]
