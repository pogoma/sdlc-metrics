#!/usr/bin/env python3
"""Gate over stored measurements (SDLC-0013).

Checks each measurement against the schema of the version it declares, not
against the newest one: a project working on an older version of the process
still writes correct measurements, and migrating them is a separate decision.

    ./scripts/validate.py                 # every file of raw/
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

import schema

GATE = "metrics:schema"
RULE = "SDLC-0013"
SUFFIX = ".json"


def repository_root(script: Path) -> Path:
    """Root of the metrics repository, taken from the script location."""
    return script.resolve().parents[1]


def measurements(root: Path, arguments: List[str]) -> List[Path]:
    """Files to check: the ones named, or the whole raw directory."""
    if arguments:
        return [Path(argument) for argument in arguments]
    place = root / schema.RAW_DIRECTORY
    if not place.is_dir():
        return []
    return sorted(path for path in place.iterdir()
                  if path.is_file() and not path.name.startswith("."))


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
    if path.suffix != SUFFIX:
        return [finding(subject, "pomiar zapisuje się jako osobny plik {}".format(SUFFIX))]
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        return [finding(subject, "nie udało się odczytać pomiaru ({})".format(error))]
    except ValueError as error:
        return [finding(subject, "nie jest poprawnym JSON-em ({})".format(error))]
    try:
        version = schema.version_of(document, path)
    except ValueError as error:
        return [finding(subject, str(error))]
    try:
        problems = schema.validate(document, version, root)
    except ValueError as error:
        return [finding(subject, str(error))]
    return [finding(subject, "wersja {}: {}".format(version, problem))
            for problem in problems]


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


def run(root: Path, arguments: List[str]) -> Dict[str, object]:
    errors: List[Dict[str, object]] = []
    notices: List[Dict[str, object]] = []
    paths = measurements(root, arguments)
    if not paths:
        notices.append(finding(GATE, "nie ma pomiarów do sprawdzenia"))
    for path in paths:
        if not path.is_file():
            errors.append(finding(named(root, path), "nie ma takiego pliku"))
            continue
        errors.extend(check_file(root, path))
    return report(errors, notices)


def main(argv: List[str]) -> int:
    root = repository_root(Path(__file__))
    document = run(root, list(argv[1:]))
    print(json.dumps(document, ensure_ascii=False, indent=2))
    return 0 if document["result"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
