#!/usr/bin/env python3
# python-file: script
"""All migrations of one measurement, from its version to the newest (SDLC-0013).

    ./scripts/migrate.py <path> [--from <version>] [--to <version>] [--apply]

Runs the migration steps one after another and hands each one the gaps the
previous one could not store, so a gap noticed on the way out of version 0
still reaches the file that ends up in the newest version. Stops at the first
step that fails and says which version it stopped on.

Without --apply only the first step runs: the steps after it need the file the
first one did not write.

Standard library only. Identifiers, docstrings and comments are English; text
printed for the owner is Polish (SDLC-0001).
"""

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

import kinds
import usage

GATE = "metrics:migrate"
RULE = "SDLC-0013"
MIGRATIONS = "migrations"
SCRIPT_NAME = "migrate_{}_to_{}.py"
# Migrations of protocol runs came first and keep their names; any other kind
# carries its name in the name of the script (SDLC-0030).
KIND_SCRIPT_NAME = "migrate_{}_{}_to_{}.py"


def repository_root(script: Path) -> Path:
    """Root of the metrics repository, taken from the script location."""
    return script.resolve().parents[1]


def migrations_directory() -> Path:
    """Directory holding one script per pair of neighbouring versions."""
    return Path(__file__).resolve().parent / MIGRATIONS


def named(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def finding(subject: str, message: str) -> Dict[str, object]:
    return {"subject": subject, "message": message, "rule": RULE}


def read(path: Path) -> object:
    return kinds.read(path)


def starting_point(root: Path, path: Path, declared: Optional[int],
                   errors: List[Dict[str, object]]) -> Optional[tuple]:
    """Kind and version the chain starts from, checked against the file."""
    subject = named(root, path)
    try:
        document = read(path)
    except (OSError, ValueError) as error:
        errors.append(finding(subject, "nie udało się odczytać pomiaru ({})".format(error)))
        return None
    try:
        found = kinds.version_of(document, path)
        kind = kinds.kind_of(document, path, root)
    except ValueError as error:
        errors.append(finding(subject, str(error)))
        return None
    if declared is not None and declared != found:
        errors.append(finding(subject, "podano wersję {}, a plik jest w wersji {}".format(
            declared, found)))
        return None
    return kind, found


def step_script(source: int, target: int, kind: str = kinds.PROCESS_KIND) -> Path:
    if kind == kinds.PROCESS_KIND:
        return migrations_directory() / SCRIPT_NAME.format(source, target)
    return migrations_directory() / KIND_SCRIPT_NAME.format(kind, source, target)


def run_step(root: Path, path: Path, source: int, target: int,
             gaps: List[Dict[str, object]], apply: bool,
             kind: str = kinds.PROCESS_KIND) -> Dict[str, object]:
    """Report of one migration script, run as its own process."""
    script = step_script(source, target, kind)
    arguments = [sys.executable, str(script), str(path), "--root", str(root)]
    if apply:
        arguments.append("--apply")
    carried = None
    if gaps:
        carried = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False,
                                              encoding="utf-8")
        json.dump(gaps, carried, ensure_ascii=False)
        carried.close()
        arguments.extend(["--carry-gaps", carried.name])
    try:
        finished = subprocess.run(arguments, capture_output=True, text=True, check=False)
    finally:
        if carried:
            Path(carried.name).unlink(missing_ok=True)
    try:
        return json.loads(finished.stdout)
    except ValueError:
        return {
            "gate": "metrics:migrate:{}-{}".format(source, target),
            "result": "FAIL",
            "counts": {"errors": 1, "notices": 0},
            "errors": [finding(named(root, script),
                               "skrypt migracji nie wypisał poprawnego JSON-a")],
            "notices": [],
            "output": (finished.stdout + finished.stderr).strip(),
        }


def run(root: Path, path: Path, declared: Optional[int], wanted: Optional[int],
        apply: bool) -> Dict[str, object]:
    """Chain of migrations of one file, as one report."""
    errors: List[Dict[str, object]] = []
    notices: List[Dict[str, object]] = []
    gates: List[Dict[str, object]] = []
    subject = named(root, path)
    if not path.is_file():
        return report([finding(subject, "nie ma takiego pliku")], notices, gates, None)
    point = starting_point(root, path, declared, errors)
    if point is None:
        return report(errors, notices, gates, None)
    kind, version = point
    try:
        target = wanted if wanted is not None else kinds.latest(kind, root)
    except ValueError as error:
        return report([finding(subject, str(error))], notices, gates, None)
    if version >= target:
        notices.append(finding(subject, "pomiar jest już w wersji {}".format(version)))
        return report(errors, notices, gates, version)
    gaps: List[Dict[str, object]] = []
    current = path
    while version < target:
        if not step_script(version, version + 1, kind).is_file():
            errors.append(finding(subject, "brak skryptu migracji z wersji {} do {}".format(
                version, version + 1)))
            break
        answer = run_step(root, current, version, version + 1, gaps, apply, kind)
        gates.append(answer)
        if answer.get("result") != "PASS":
            errors.append(finding(subject, "migracja stanęła na wersji {}".format(version)))
            break
        gaps = answer.get("gaps") or []
        version += 1
        if not apply:
            notices.append(finding(subject, "bez --apply wykonano tylko pierwszy krok; "
                                            "kolejne potrzebują zapisanego pliku"))
            break
        current = root / str(answer.get("target"))
    return report(errors, notices, gates, version)


def report(errors: List[Dict[str, object]], notices: List[Dict[str, object]],
           gates: List[Dict[str, object]], version: Optional[int]) -> Dict[str, object]:
    return {
        "gate": GATE,
        "result": "PASS" if not errors else "FAIL",
        "counts": {"errors": len(errors), "notices": len(notices)},
        "errors": errors,
        "notices": notices,
        "gates": gates,
        "version": version,
        "target": gates[-1].get("target") if gates else None,
    }


def parse(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Migracja jednego pomiaru do najnowszej wersji schematu.")
    parser.add_argument("path")
    parser.add_argument("--from", dest="source", type=int, default=None)
    parser.add_argument("--to", dest="target", type=int, default=None)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--root", default=None)
    return parser.parse_args(argv[1:])


USAGE_COMMANDS = (usage.command(
    usage.PLAIN_COMMAND,
    "Przenosi jeden pomiar na najnowszą wersję schematu.",
    changes=True,
    arguments=[
        usage.described("<ścieżka>", "Plik pomiaru do migracji."),
        usage.described("--from", "Wersja początkowa, gdy pomiar jej nie niesie."),
        usage.described("--to", "Wersja docelowa migracji."),
        usage.described("--root", "Korzeń repozytorium metryk."),
        usage.described("--apply", "Zgoda na zapis; bez niej tylko raport."),
    ],
    confirms=[
        usage.described("pomiar", "Plik niesie wersję docelową schematu."),
    ],
),)


def main(argv: List[str]) -> int:
    if usage.asked(argv):
        return usage.emit(usage.report(
            "migrate.py", USAGE_COMMANDS))
    options = parse(argv)
    root = Path(options.root) if options.root else repository_root(Path(__file__))
    document = run(root, Path(options.path), options.source, options.target,
                   options.apply)
    print(json.dumps(document, ensure_ascii=False, indent=2))
    return 0 if document["result"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
