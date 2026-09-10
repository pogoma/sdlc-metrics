#!/usr/bin/env python3
"""Tests of the migration of a whole directory."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import migrate_all
import schema

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
        source = schema.directory(schema.repository_root(Path(schema.__file__)))
        target = self.root / schema.SCHEMAS_DIRECTORY
        target.mkdir(parents=True)
        for path in source.glob("*.json"):
            (target / path.name).write_text(path.read_text(encoding="utf-8"),
                                            encoding="utf-8")
        (self.root / schema.RAW_DIRECTORY).mkdir()
        (self.root / schema.LEGACY_DIRECTORY).mkdir()

    def write(self, name: str, document: object, directory: str) -> Path:
        path = self.root / directory / name
        path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
        return path

    def raw(self) -> list:
        return sorted(path.name for path in (self.root / schema.RAW_DIRECTORY).iterdir())

    def test_mixed_directory(self) -> None:
        self.write("sdlc-A-20260101T120000Z.json", VERSION_ONE, schema.RAW_DIRECTORY)
        self.write("sdlc-A-20260102T120000Z.json",
                   dict(VERSION_ONE, finished="20260102T120000Z"),
                   schema.RAW_DIRECTORY)
        self.write("gotowy.json",
                   dict(VERSION_ONE, schema_version=2, uid="a" * 32, migration_gaps=[]),
                   schema.RAW_DIRECTORY)
        found = migrate_all.run(self.root, schema.RAW_DIRECTORY, True)
        self.assertEqual(found["result"], "PASS")
        self.assertEqual(len(self.raw()), 3)
        self.assertIn("gotowy.json", self.raw())

    def test_files_written_by_the_migration_are_not_migrated_again(self) -> None:
        self.write("sdlc-A-20260101T120000Z.json", VERSION_ONE, schema.RAW_DIRECTORY)
        found = migrate_all.run(self.root, schema.RAW_DIRECTORY, True)
        self.assertEqual(found["result"], "PASS")
        self.assertEqual(len(found["gates"]), 1)
        self.assertEqual(len(self.raw()), 1)

    def test_empty_directory(self) -> None:
        found = migrate_all.run(self.root, schema.RAW_DIRECTORY, True)
        self.assertEqual(found["result"], "PASS")
        self.assertEqual(found["counts"]["notices"], 1)

    def test_one_broken_file_does_not_stop_the_others(self) -> None:
        self.write("sdlc-A-20260101T120000Z.json", VERSION_ONE, schema.RAW_DIRECTORY)
        broken = dict(VERSION_ONE)
        del broken["agent"]
        self.write("zly.json", broken, schema.RAW_DIRECTORY)
        found = migrate_all.run(self.root, schema.RAW_DIRECTORY, True)
        self.assertEqual(found["result"], "FAIL")
        self.assertEqual(len(found["errors"]), 1)
        self.assertIn("zly.json", found["errors"][0]["subject"])
        self.assertIn("zly.json", self.raw())
        self.assertEqual(len([name for name in self.raw() if name.startswith("2026")]), 1)

    def test_legacy_directory(self) -> None:
        self.write("agent-skills-protokol-a-b-20260820T192700Z.json",
                   VERSION_ZERO, schema.LEGACY_DIRECTORY)
        found = migrate_all.run(self.root, schema.LEGACY_DIRECTORY, True)
        self.assertEqual(found["result"], "PASS")
        self.assertEqual(list((self.root / schema.LEGACY_DIRECTORY).iterdir()), [])
        self.assertEqual(len(self.raw()), 1)

    def test_without_apply_nothing_changes(self) -> None:
        self.write("sdlc-A-20260101T120000Z.json", VERSION_ONE, schema.RAW_DIRECTORY)
        found = migrate_all.run(self.root, schema.RAW_DIRECTORY, False)
        self.assertEqual(found["result"], "PASS")
        self.assertEqual(self.raw(), ["sdlc-A-20260101T120000Z.json"])

    def test_directory_that_does_not_exist(self) -> None:
        found = migrate_all.run(self.root, "nie-ma", True)
        self.assertEqual(found["result"], "PASS")
        self.assertIn("nie ma pomiarów do migracji", found["notices"][0]["message"])


if __name__ == "__main__":
    unittest.main()
