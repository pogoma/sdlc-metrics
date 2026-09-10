#!/usr/bin/env python3
"""Reading a measurement schema and checking a document against it (SDLC-0013).

A schema lives in schemas/<version>.json of this repository and is the only
description of what a measurement of that version looks like. The checker
covers a closed subset of the JSON Schema 2020-12 vocabulary:

    type, properties, required, additionalProperties, items, enum, pattern,
    minimum, maximum, minItems, minLength, maxLength, $ref

These annotations are read and ignored: $schema, $id, $comment, title,
description, examples, default, $defs. Any other keyword is reported as a
problem instead of passing silently, so a schema cannot promise a rule the
checker does not apply.

A $ref points inside the same schema, as "#/$defs/<name>". Keywords standing
next to a $ref are applied after it.

Standard library only. Identifiers, docstrings and comments are English; text
printed for the owner is Polish (SDLC-0001).
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Optional

SCHEMAS_DIRECTORY = "schemas"
RAW_DIRECTORY = "raw"
LEGACY_DIRECTORY = "legacy"
VERSION_FIELD = "schema_version"
VERSION_NAME = re.compile(r"^(\d+)\.json$")
REFERENCE_PREFIX = "#/$defs/"

# Keywords the checker applies. Everything outside both sets is a problem.
KEYWORDS = ("$ref", "type", "properties", "required", "additionalProperties",
            "items", "enum", "pattern", "minimum", "maximum", "minItems",
            "minLength", "maxLength")
ANNOTATIONS = ("$schema", "$id", "$comment", "$defs", "title", "description",
               "examples", "default")

TYPES = {
    "object": "obiektem",
    "array": "listą",
    "string": "tekstem",
    "integer": "liczbą całkowitą",
    "number": "liczbą",
    "boolean": "wartością logiczną",
    "null": "wartością pustą",
}


def repository_root(module: Path) -> Path:
    """Root of the metrics repository, taken from the module location."""
    return module.resolve().parents[1]


def directory(root: Optional[Path] = None) -> Path:
    """Directory holding one schema file per version."""
    base = root if root is not None else repository_root(Path(__file__))
    return base / SCHEMAS_DIRECTORY


def versions(root: Optional[Path] = None) -> List[int]:
    """Versions that have a schema, in ascending order."""
    found = []
    place = directory(root)
    if not place.is_dir():
        return found
    for path in sorted(place.iterdir()):
        match = VERSION_NAME.match(path.name)
        if match:
            found.append(int(match.group(1)))
    return sorted(found)


def latest(root: Optional[Path] = None) -> int:
    """Newest version that has a schema."""
    found = versions(root)
    if not found:
        raise ValueError("brak katalogu schematów albo żadnego schematu wersji")
    return found[-1]


def load(version: int, root: Optional[Path] = None) -> Dict[str, object]:
    """Schema of one version, as a document."""
    path = directory(root) / "{}.json".format(version)
    if not path.is_file():
        raise ValueError("brak schematu wersji {}".format(version))
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError("schemat wersji {} nie jest obiektem".format(version))
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


def validate(document: object, version: int,
             root: Optional[Path] = None) -> List[str]:
    """Everything wrong with one measurement, as a list of Polish sentences."""
    schema = load(version, root)
    return check(document, schema, schema, "pomiar")


def resolve(schema: Dict[str, object], top: Dict[str, object],
            label: str, problems: List[str]) -> Optional[Dict[str, object]]:
    """Schema a $ref points at, or None when the reference leads nowhere."""
    reference = schema.get("$ref")
    if not isinstance(reference, str) or not reference.startswith(REFERENCE_PREFIX):
        problems.append("schemat pola {}: $ref {} nie wskazuje definicji w tym "
                        "schemacie".format(label, reference))
        return None
    definitions = top.get("$defs")
    name = reference[len(REFERENCE_PREFIX):]
    if not isinstance(definitions, dict) or not isinstance(definitions.get(name), dict):
        problems.append("schemat pola {}: brak definicji {}".format(label, name))
        return None
    return definitions[name]


def check(value: object, schema: object, top: Dict[str, object],
          label: str) -> List[str]:
    """Problems of one value against one schema, its own label included."""
    problems: List[str] = []
    if not isinstance(schema, dict):
        problems.append("schemat pola {} nie jest obiektem".format(label))
        return problems
    unknown = sorted(set(schema) - set(KEYWORDS) - set(ANNOTATIONS))
    if unknown:
        problems.append("schemat pola {}: słowo kluczowe spoza podzbioru: {}".format(
            label, ", ".join(unknown)))
        return problems
    if "$ref" in schema:
        target = resolve(schema, top, label, problems)
        if target is None:
            return problems
        problems.extend(check(value, target, top, label))
    check_type(value, schema, label, problems)
    if problems:
        return problems
    check_scalar(value, schema, label, problems)
    check_object(value, schema, top, label, problems)
    check_array(value, schema, top, label, problems)
    return problems


def check_type(value: object, schema: Dict[str, object], label: str,
               problems: List[str]) -> None:
    expected = schema.get("type")
    if expected is None:
        return
    if not isinstance(expected, str) or expected not in TYPES:
        problems.append("schemat pola {}: type {} spoza podzbioru".format(label, expected))
        return
    if not matches_type(value, expected):
        problems.append("{} nie jest {}".format(label, TYPES[expected]))


def matches_type(value: object, expected: str) -> bool:
    if expected == "boolean":
        return isinstance(value, bool)
    if isinstance(value, bool):
        return False
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int)
    if expected == "number":
        return isinstance(value, (int, float))
    return value is None


def check_scalar(value: object, schema: Dict[str, object], label: str,
                 problems: List[str]) -> None:
    if "enum" in schema and value not in schema["enum"]:
        problems.append("{} ma wartość spoza listy dopuszczonych: {}".format(
            label, ", ".join(str(item) for item in schema["enum"])))
    if isinstance(value, str):
        pattern = schema.get("pattern")
        if isinstance(pattern, str) and not re.search(pattern, value):
            problems.append("{} nie pasuje do wzorca {}".format(label, pattern))
        limit = schema.get("minLength")
        if isinstance(limit, int) and len(value) < limit:
            problems.append("{} jest krótsze niż {} znaków".format(label, limit))
        limit = schema.get("maxLength")
        if isinstance(limit, int) and len(value) > limit:
            problems.append("{} ma {} znaków, limit to {}".format(
                label, len(value), limit))
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        limit = schema.get("minimum")
        if isinstance(limit, (int, float)) and value < limit:
            problems.append("{} jest mniejsze niż {}".format(label, limit))
        limit = schema.get("maximum")
        if isinstance(limit, (int, float)) and value > limit:
            problems.append("{} jest większe niż {}".format(label, limit))


def check_object(value: object, schema: Dict[str, object], top: Dict[str, object],
                 label: str, problems: List[str]) -> None:
    if not isinstance(value, dict):
        return
    properties = schema.get("properties")
    properties = properties if isinstance(properties, dict) else {}
    required = schema.get("required")
    for name in required if isinstance(required, list) else []:
        if name not in value:
            problems.append("{}: brak pola {}".format(label, name))
    extra = sorted(set(value) - set(properties))
    additional = schema.get("additionalProperties")
    if additional is False and extra:
        problems.append("{}: pole spoza schematu: {}".format(label, ", ".join(extra)))
    for name, item in sorted(value.items()):
        place = "{}.{}".format(label, name)
        if name in properties:
            problems.extend(check(item, properties[name], top, place))
        elif isinstance(additional, dict):
            problems.extend(check(item, additional, top, place))


def check_array(value: object, schema: Dict[str, object], top: Dict[str, object],
                label: str, problems: List[str]) -> None:
    if not isinstance(value, list):
        return
    limit = schema.get("minItems")
    if isinstance(limit, int) and len(value) < limit:
        problems.append("{} ma mniej niż {} elementów".format(label, limit))
    items = schema.get("items")
    if not isinstance(items, dict):
        return
    for number, item in enumerate(value):
        problems.extend(check(item, items, top, "{}[{}]".format(label, number)))
