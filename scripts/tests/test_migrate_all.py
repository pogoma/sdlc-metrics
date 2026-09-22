#!/usr/bin/env python3
"""Tests of the migration of a whole directory."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import migrate_all
import kinds

# Schemas and measurements live in the directory of their kind (SDLC-0030).
SCHEMAS = "{}/{}".format(kinds.SCHEMAS_DIRECTORY, kinds.PROCESS_KIND)
RAW = "{}/{}".format(kinds.RAW_DIRECTORY, kinds.PROCESS_KIND)

VERSION_ZERO = {
    "project": "agent-skills",
    "process": "protokol-a-b",
    "run_id": "af41ec7",
    "measurements": {"plan_questions": {"definition": "liczba pytań", "value": 2}},
}

VERSION_ONE = {
    "protocol": "A",
    "name": "planowanie zmiany",
    "project": "sdlc",
    "agent": {"name": "agent", "sessions": ["sesja"]},
    "description": "Przebieg próbny.",
    "interactions": 1,
    "corrections": [],
    "measurements": {"plan_questions": {"definition": "pytania", "value": 2}},
    "finished": "20260101T120000Z",
}


class MigrateAllTest(unittest.TestCase):
    def setUp(self) -> None:
        self.place = tempfile.TemporaryDirectory()
        self.root = Path(self.place.name)
        self.addCleanup(self.place.cleanup)
        source = kinds.directory(kinds.PROCESS_KIND,
                                 kinds.repository_root(Path(kinds.__file__)))
        target = self.root / SCHEMAS
        target.mkdir(parents=True)
        for path in source.glob("*.yaml"):
            (target / path.name).write_text(path.read_text(encoding="utf-8"),
                                            encoding="utf-8")
        (self.root / RAW).mkdir(parents=True)
        (self.root / kinds.LEGACY_DIRECTORY).mkdir()

    def write(self, name: str, document: object, directory: str) -> Path:
        path = self.root / directory / name
        path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
        return path

    def raw(self) -> list:
        return sorted(path.name for path in (self.root / RAW).iterdir())

    def test_mixed_directory(self) -> None:
        self.write("sdlc-A-20260101T120000Z.json", VERSION_ONE, RAW)
        self.write("sdlc-A-20260102T120000Z.json",
                   dict(VERSION_ONE, finished="20260102T120000Z"),
                   RAW)
        ready = {key: value for key, value in VERSION_ONE.items() if key != "agent"}
        ready.update(schema_version=3, uid="a" * 32, migration_gaps=[],
                     agents=[{"name": "Claude Code", "model": "claude-opus-5",
                              "sessions": ["s"]}])
        self.write("gotowy.yaml", ready, RAW)
        found = migrate_all.run(self.root, RAW, True)
        self.assertEqual(found["result"], "PASS")
        self.assertEqual(len(self.raw()), 3)
        self.assertIn("gotowy.yaml", self.raw())

    def test_files_written_by_the_migration_are_not_migrated_again(self) -> None:
        self.write("sdlc-A-20260101T120000Z.json", VERSION_ONE, RAW)
        found = migrate_all.run(self.root, RAW, True)
        self.assertEqual(found["result"], "PASS")
        self.assertEqual(len(found["gates"]), 1)
        self.assertEqual(len(self.raw()), 1)

    def test_empty_directory(self) -> None:
        found = migrate_all.run(self.root, RAW, True)
        self.assertEqual(found["result"], "PASS")
        self.assertEqual(found["counts"]["notices"], 1)

    def test_one_broken_file_does_not_stop_the_others(self) -> None:
        self.write("sdlc-A-20260101T120000Z.json", VERSION_ONE, RAW)
        broken = dict(VERSION_ONE)
        del broken["agent"]
        self.write("zly.json", broken, RAW)
        found = migrate_all.run(self.root, RAW, True)
        self.assertEqual(found["result"], "FAIL")
        self.assertEqual(len(found["errors"]), 1)
        self.assertIn("zly.json", found["errors"][0]["subject"])
        self.assertIn("zly.json", self.raw())
        self.assertEqual(len([name for name in self.raw() if name.startswith("2026")]), 1)

    def test_reports_keep_the_order_of_the_files(self) -> None:
        """The pool answers in the order of the files, not of finishing."""
        for day in range(1, 6):
            self.write("sdlc-A-2026010{}T120000Z.json".format(day),
                       dict(VERSION_ONE, finished="2026010{}T120000Z".format(day)),
                       RAW)
        found = migrate_all.run(self.root, RAW, False)
        self.assertEqual(found["result"], "PASS")
        self.assertEqual(len(found["gates"]), 5)
        subjects = [gate.get("subject") or "" for gate in found["gates"]]
        self.assertEqual(subjects, sorted(subjects))

    def test_one_worker_gives_the_same_report_as_many(self) -> None:
        """The migration gives every measurement a fresh uid, so the parts
        compared here are the ones that must not depend on the pool."""
        for day in range(1, 5):
            self.write("sdlc-A-2026010{}T120000Z.json".format(day),
                       dict(VERSION_ONE, finished="2026010{}T120000Z".format(day)),
                       RAW)

        def stable(gates):
            return [(gate.get("gate"), gate.get("result"), gate.get("subject"))
                    for gate in gates]

        many = migrate_all.run(self.root, RAW, False)
        paths = migrate_all.measurements(self.root / RAW)
        one = [migrate_all.run_one(self.root, path, False) for path in paths]
        self.assertEqual(stable(many["gates"]), stable(one))

    def test_jobs_never_exceed_the_files_to_migrate(self) -> None:
        self.assertEqual(migrate_all.jobs_for(0), 1)
        self.assertEqual(migrate_all.jobs_for(1), 1)
        self.assertLessEqual(migrate_all.jobs_for(2), 2)
        self.assertLessEqual(migrate_all.jobs_for(10000),
                             max(1, os.cpu_count() or 1))

    def test_no_files_need_no_pool(self) -> None:
        self.assertEqual(migrate_all.run_many(self.root, [], False), [])

    def test_legacy_directory(self) -> None:
        self.write("agent-skills-protokol-a-b-20260820T192700Z.json",
                   VERSION_ZERO, kinds.LEGACY_DIRECTORY)
        found = migrate_all.run(self.root, kinds.LEGACY_DIRECTORY, True)
        self.assertEqual(found["result"], "PASS")
        self.assertEqual(list((self.root / kinds.LEGACY_DIRECTORY).iterdir()), [])
        self.assertEqual(len(self.raw()), 1)

    def test_without_apply_nothing_changes(self) -> None:
        self.write("sdlc-A-20260101T120000Z.json", VERSION_ONE, RAW)
        found = migrate_all.run(self.root, RAW, False)
        self.assertEqual(found["result"], "PASS")
        self.assertEqual(self.raw(), ["sdlc-A-20260101T120000Z.json"])

    def test_directory_that_does_not_exist(self) -> None:
        found = migrate_all.run(self.root, "nie-ma", True)
        self.assertEqual(found["result"], "PASS")
        self.assertIn("nie ma pomiarów do migracji", found["notices"][0]["message"])


if __name__ == "__main__":
    unittest.main()
