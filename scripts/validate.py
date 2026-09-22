#!/usr/bin/env python3
# python-file: script
"""Gate over stored measurements (SDLC-0013).

Checks each measurement against the schema of the kind and version it declares,
not against the newest one: a project working on an older version of the
process still writes correct measurements, and migrating them is a separate
decision. A measurement of an unknown kind is a refusal, not a file left out.

    ./scripts/validate.py                 # every file of raw/<kind>/
    ./scripts/validate.py <path>…         # the files named

Prints one JSON report and repeats the result in the exit code: 0 for PASS,
1 for FAIL, 2 for a call it cannot make sense of.

Standard library only. Identifiers, docstrings and comments are English; text
printed for the owner is Polish (SDLC-0001).
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

import convention
import kinds
import usage

GATE = "metrics:schema"
RULE = "SDLC-0013"
SUFFIXES = (".json", ".yaml")


def repository_root(script: Path) -> Path:
    """Root of the metrics repository, taken from the script location."""
    return script.resolve().parents[1]


def measurements(root: Path, arguments: List[str]) -> List[Path]:
    """Files to check: the ones named, or every kind of the raw directory."""
    if arguments:
        return [Path(argument) for argument in arguments]
    place = root / kinds.RAW_DIRECTORY
    if not place.is_dir():
        return []
    found = []
    for kind in sorted(path for path in place.iterdir() if path.is_dir()):
        found.extend(path for path in sorted(kind.iterdir())
                     if path.is_file() and not path.name.startswith("."))
    return found


def named(root: Path, path: Path) -> str:
    """Path as the owner reads it: relative to the repository when it lies inside."""
    try:
        return path.resolve().relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def finding(subject: str, message: str) -> Dict[str, object]:
    return {"subject": subject, "message": message, "rule": RULE}


def check_file(root: Path, path: Path) -> List[Dict[str, object]]:
    """Problems of one measurement, each as a finding."""
    subject = named(root, path)
    if path.suffix not in SUFFIXES:
        return [finding(subject, "pomiar zapisuje się jako osobny plik {}".format(
            " albo ".join(SUFFIXES)))]
    try:
        document = kinds.read(path)
    except ValueError as error:
        return [finding(subject, "nie udało się odczytać pomiaru ({})".format(error))]
    try:
        version = kinds.version_of(document, path)
    except ValueError as error:
        return [finding(subject, str(error))]
    try:
        kind = kinds.kind_of(document, path, root)
    except ValueError as error:
        return [finding(subject, str(error))]
    try:
        problems = kinds.validate(document, version, root, kind)
    except ValueError as error:
        return [finding(subject, str(error))]
    found = [finding(subject, "rodzaj {}, wersja {}: {}".format(kind, version, problem))
             for problem in problems]
    expected = kinds.suffix_for(kind, version)
    if path.suffix != expected:
        found.append(finding(subject, "pomiar rodzaju {} w wersji {} zapisuje się jako "
                                      "plik {}".format(kind, version, expected)))
    return found


def report(errors: List[Dict[str, object]],
           notices: Optional[List[Dict[str, object]]] = None) -> Dict[str, object]:
    notices = notices or []
    return {
        "gate": GATE,
        "result": "PASS" if not errors else "FAIL",
        "counts": {"errors": len(errors), "notices": len(notices)},
        "errors": errors,
        "notices": notices,
    }


def schema_files(root: Path) -> List[Dict[str, object]]:
    """Schemas written in anything but YAML (SDLC-0042)."""
    place = root / kinds.SCHEMAS_DIRECTORY
    if not place.is_dir():
        return []
    return [finding(named(root, path), "schemat zapisuje się jako plik <wersja>{}".format(
                kinds.SCHEMA_SUFFIX))
            for kind in sorted(path for path in place.iterdir() if path.is_dir())
            for path in sorted(kind.iterdir())
            if path.is_file() and not kinds.VERSION_NAME.match(path.name)]


def run(root: Path, arguments: List[str]) -> Dict[str, object]:
    errors: List[Dict[str, object]] = schema_files(root)
    notices: List[Dict[str, object]] = []
    try:
        convention.validator()
    except convention.MissingLibrary as error:
        errors.append(finding(GATE, str(error)))
        return report(errors, notices)
    paths = measurements(root, arguments)
    if not paths:
        notices.append(finding(GATE, "nie ma pomiarów do sprawdzenia"))
    for path in paths:
        if not path.is_file():
            errors.append(finding(named(root, path), "nie ma takiego pliku"))
            continue
        errors.extend(check_file(root, path))
    return report(errors, notices)


USAGE_COMMANDS = (usage.command(
    usage.PLAIN_COMMAND,
    "Sprawdza pomiary repozytorium wobec ich schematów.",
    changes=False,
),)


def main(argv: List[str]) -> int:
    if usage.asked(argv):
        return usage.emit(usage.report(
            "validate.py", USAGE_COMMANDS))
    root = repository_root(Path(__file__))
    document = run(root, list(argv[1:]))
    print(json.dumps(document, ensure_ascii=False, indent=2))
    return 0 if document["result"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
