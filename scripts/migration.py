#!/usr/bin/env python3
"""Machinery of one migration step between two versions (SDLC-0013).

Every migration script does the same thing in the same order, so the order
lives here and a script says only what its two versions differ by:

1. read the file and check that its version is the one this step starts from;
2. check it against the schema of that version — a file that does not fit is
   left untouched, because migrating a broken measurement hides the breakage;
3. carry the content over and note every field the step could not fill;
4. write the result under the name of the target version and check it against
   the schema of that version;
5. when it fits, remove the input; when it does not, put the result in
   damaged/ and remove the input anyway, so one measurement never exists in
   two versions at once.

A version whose schema has no place for gaps cannot store them, so the step
reports them and the next step takes them over through --carry-gaps. That is
how a gap noticed on the way out of version 0 still reaches the file that ends
up in version 2.

Without --apply nothing is written, moved or removed.

Standard library only. Identifiers, docstrings and comments are English; text
printed for the owner is Polish (SDLC-0001).
"""

import argparse
import json
import re
import uuid
from pathlib import Path
from typing import Callable, Dict, List, Optional

import schema

DAMAGED_DIRECTORY = "damaged"
RULE = "SDLC-0013"
STAMP = re.compile(r"(\d{8}T\d{6}Z)")

Transform = Callable[[Dict[str, object], List[Dict[str, object]], Path],
                     Dict[str, object]]
Name = Callable[[Dict[str, object], Path], str]


def repository_root(script: Path) -> Path:
    """Root of the metrics repository, taken from the script location."""
    return script.resolve().parents[2]


def new_uid() -> str:
    """Identifier of one protocol call: a version 4 UUID without dashes."""
    return uuid.uuid4().hex


def gap(field: str, from_version: int, reason: str) -> Dict[str, object]:
    """One field the migration could not fill from the source file."""
    return {"field": field, "from_version": from_version, "reason": reason}


def stamp_of(document: Dict[str, object], path: Path) -> Optional[str]:
    """Time marker of the run: from the content, or from the file name."""
    for key in ("finished", "started"):
        value = document.get(key)
        if isinstance(value, str) and re.fullmatch(r"\d{8}T\d{6}Z", value):
            return value
    match = STAMP.search(path.name)
    return match.group(1) if match else None


def named(root: Path, path: Path) -> str:
    """Path as the owner reads it: relative to the repository when it lies inside."""
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


class Report:
    """What one migration step has to say, in the shape of a gate report."""

    def __init__(self, gate: str) -> None:
        self.gate = gate
        self.errors: List[Dict[str, object]] = []
        self.notices: List[Dict[str, object]] = []
        self.actions: List[str] = []
        self.gaps: List[Dict[str, object]] = []
        self.target: Optional[str] = None

    def fail(self, subject: str, message: str) -> None:
        self.errors.append({"subject": subject, "message": message, "rule": RULE})

    def notice(self, subject: str, message: str) -> None:
        self.notices.append({"subject": subject, "message": message, "rule": RULE})

    def action(self, message: str) -> None:
        self.actions.append(message)

    def as_document(self) -> Dict[str, object]:
        return {
            "gate": self.gate,
            "result": "PASS" if not self.errors else "FAIL",
            "counts": {"errors": len(self.errors), "notices": len(self.notices)},
            "errors": self.errors,
            "notices": self.notices,
            "actions": self.actions,
            "gaps": self.gaps,
            "target": self.target,
        }


def read_carried(path: Optional[str], report: Report) -> List[Dict[str, object]]:
    """Gaps an earlier step could not store, handed over on the call."""
    if not path:
        return []
    try:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        report.fail(report.gate, "nie udało się odczytać braków z {} ({})".format(
            path, error))
        return []
    if not isinstance(document, list):
        report.fail(report.gate, "{} nie zawiera listy braków".format(path))
        return []
    return document


def migrate(root: Path, path: Path, source: int, target: int, transform: Transform,
            name: Name, carried: List[Dict[str, object]], apply: bool) -> Report:
    """One step of migration, from reading the file to removing it."""
    report = Report("metrics:migrate:{}-{}".format(source, target))
    subject = named(root, path)
    document = read_measurement(path, subject, report)
    if document is None:
        return report
    if not correct_version(document, path, source, subject, report):
        return report
    problems = schema.validate(document, source, root)
    if problems:
        for problem in problems:
            report.fail(subject, "wersja {}: {}".format(source, problem))
        report.notice(subject, "plik zostaje nietknięty; migracja nie naprawia pomiaru "
                               "niezgodnego ze swoją wersją")
        return report
    gaps = list(carried)
    result = transform(document, gaps, path)
    report.gaps = gaps
    place = root / schema.RAW_DIRECTORY / name(result, path)
    if place.exists():
        report.fail(subject, "{}: plik o tej nazwie już istnieje".format(
            named(root, place)))
        return report
    problems = schema.validate(result, target, root)
    if problems:
        store_damaged(root, path, place.name, result, problems, subject, report, apply)
        return report
    report.target = named(root, place)
    report.action("zapisz {}".format(report.target))
    report.action("usuń {}".format(subject))
    if apply:
        write(place, result)
        path.unlink()
    else:
        report.notice(subject, "bez --apply nic nie zostało zmienione")
    return report


def read_measurement(path: Path, subject: str,
                     report: Report) -> Optional[Dict[str, object]]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        report.fail(subject, "nie udało się odczytać pomiaru ({})".format(error))
        return None
    except ValueError as error:
        report.fail(subject, "nie jest poprawnym JSON-em ({})".format(error))
        return None
    if not isinstance(document, dict):
        report.fail(subject, "pomiar nie jest obiektem")
        return None
    return document


def correct_version(document: Dict[str, object], path: Path, source: int,
                    subject: str, report: Report) -> bool:
    try:
        found = schema.version_of(document, path)
    except ValueError as error:
        report.fail(subject, str(error))
        return False
    if found != source:
        report.fail(subject, "plik jest w wersji {}, a ten skrypt migruje z wersji "
                             "{}".format(found, source))
        return False
    return True


def store_damaged(root: Path, path: Path, name: str, result: Dict[str, object],
                  problems: List[str], subject: str, report: Report,
                  apply: bool) -> None:
    """Result that does not fit its own version, and the input that made it."""
    place = root / DAMAGED_DIRECTORY / name
    for problem in problems:
        report.fail(subject, "po migracji: {}".format(problem))
    report.target = named(root, place)
    report.action("przenieś wynik do {}".format(report.target))
    report.action("usuń {}".format(subject))
    if apply:
        write(place, result)
        path.unlink()
    else:
        report.notice(subject, "bez --apply nic nie zostało zmienione")


def write(path: Path, document: Dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")


def parse(argv: List[str], source: int, target: int) -> argparse.Namespace:
    """Call of a migration script: one file, and what to do with it."""
    parser = argparse.ArgumentParser(
        description="Migracja pomiaru z wersji {} do wersji {}.".format(source, target))
    parser.add_argument("path")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--carry-gaps", dest="carry_gaps", default=None)
    parser.add_argument("--root", default=None)
    return parser.parse_args(argv[1:])


def main(argv: List[str], script: Path, source: int, target: int,
         transform: Transform, name: Name) -> int:
    """Entry point every migration script shares."""
    options = parse(argv, source, target)
    root = Path(options.root) if options.root else repository_root(script)
    report = Report("metrics:migrate:{}-{}".format(source, target))
    carried = read_carried(options.carry_gaps, report)
    if not report.errors:
        report = migrate(root, Path(options.path), source, target, transform, name,
                         carried, options.apply)
    document = report.as_document()
    print(json.dumps(document, ensure_ascii=False, indent=2))
    return 0 if document["result"] == "PASS" else 1
