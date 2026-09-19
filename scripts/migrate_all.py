#!/usr/bin/env python3
# python-file: script
"""Migration of every measurement in one directory (SDLC-0013).

    ./scripts/migrate_all.py [--directory raw] [--apply]

Runs migrate.py for each file of the directory and gives one result. The list
of files is taken before the first migration, so measurements written by the
migration itself are not migrated again in the same pass.

The files go to a pool instead of being waited for one at a time: each one is
a subprocess this script only waits for, and their number grows with the
repository. The reports come back in the order of the files, never in the
order they finished, because one run of this script is compared with the next
(PYTHON-0007). The pool lives here rather than in a shared library, because
this repository holds measurements and mounts no convention of its own.

One file that cannot be migrated does not stop the others: the run goes to the
end and the report says which files failed.

Standard library only. Identifiers, docstrings and comments are English; text
printed for the owner is Polish (SDLC-0001).
"""

import argparse
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, List

import schema
import usage

GATE = "metrics:migrate:all"
RULE = "SDLC-0013"
SCRIPT = "migrate.py"


def repository_root(script: Path) -> Path:
    """Root of the metrics repository, taken from the script location."""
    return script.resolve().parents[1]


def named(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def finding(subject: str, message: str) -> Dict[str, object]:
    return {"subject": subject, "message": message, "rule": RULE}


def measurements(place: Path) -> List[Path]:
    """Files to migrate, listed before the first one is written."""
    if not place.is_dir():
        return []
    return sorted(path for path in place.iterdir()
                  if path.is_file() and not path.name.startswith("."))


def run_one(root: Path, path: Path, apply: bool) -> Dict[str, object]:
    """Report of migrate.py for one file, run as its own process."""
    script = Path(__file__).resolve().parent / SCRIPT
    arguments = [sys.executable, str(script), str(path), "--root", str(root)]
    if apply:
        arguments.append("--apply")
    finished = subprocess.run(arguments, capture_output=True, text=True, check=False)
    try:
        return json.loads(finished.stdout)
    except ValueError:
        return {
            "gate": "metrics:migrate",
            "result": "FAIL",
            "counts": {"errors": 1, "notices": 0},
            "errors": [finding(named(root, path),
                               "migrate.py nie wypisał poprawnego JSON-a")],
            "notices": [],
            "output": (finished.stdout + finished.stderr).strip(),
        }


def jobs_for(count: int) -> int:
    """How many files to migrate side by side, for that many of them.

    The number of cores, because migrating one file is a subprocess doing real
    work. Never more than there is to do, and never fewer than one.
    """
    if count <= 1:
        return 1
    return max(1, min(os.cpu_count() or 1, count))


def run_many(root: Path, paths: List[Path], apply: bool) -> List[Dict[str, object]]:
    """Reports of every file, in the order of the files."""
    if not paths:
        return []
    workers = jobs_for(len(paths))
    if workers == 1:
        return [run_one(root, path, apply) for path in paths]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(run_one, root, path, apply) for path in paths]
        return [future.result() for future in futures]


def run(root: Path, directory: str, apply: bool) -> Dict[str, object]:
    place = root / directory
    paths = measurements(place)
    gates: List[Dict[str, object]] = []
    errors: List[Dict[str, object]] = []
    notices: List[Dict[str, object]] = []
    if not paths:
        notices.append(finding(directory, "nie ma pomiarów do migracji"))
    for path, answer in zip(paths, run_many(root, paths, apply)):
        gates.append(answer)
        if answer.get("result") != "PASS":
            errors.append(finding(named(root, path), "migracja nie przeszła"))
        notices.extend(answer.get("notices") or [])
    return {
        "gate": GATE,
        "result": "PASS" if not errors else "FAIL",
        "counts": {"errors": len(errors), "notices": len(notices)},
        "errors": errors,
        "notices": notices,
        "gates": gates,
    }


def parse(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Migracja wszystkich pomiarów jednego katalogu.")
    parser.add_argument("--directory", default="{}/{}".format(
        schema.RAW_DIRECTORY, schema.PROCESS_KIND))
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--root", default=None)
    return parser.parse_args(argv[1:])


USAGE_COMMANDS = (usage.command(
    usage.PLAIN_COMMAND,
    "Migruje wszystkie pomiary jednego katalogu.",
    changes=True,
    arguments=[
        usage.described("--directory", "Katalog pomiarów do migracji."),
        usage.described("--root", "Korzeń repozytorium metryk."),
        usage.described("--apply", "Zgoda na zapis; bez niej tylko raport."),
    ],
    confirms=[
        usage.described("pomiary", "Każdy plik katalogu niesie najnowszą wersję schematu."),
    ],
),)


def main(argv: List[str]) -> int:
    if usage.asked(argv):
        return usage.emit(usage.report(
            "migrate_all.py", USAGE_COMMANDS))
    options = parse(argv)
    root = Path(options.root) if options.root else repository_root(Path(__file__))
    document = run(root, options.directory, options.apply)
    print(json.dumps(document, ensure_ascii=False, indent=2))
    return 0 if document["result"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
