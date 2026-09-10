#!/usr/bin/env python3
"""Tests of the chain of migrations of one measurement."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import migrate
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


class MigrateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.place = tempfile.TemporaryDirectory()
        self.root = Path(self.place.name)
        self.addCleanup(self.place.cleanup)
        source = schema.directory(schema.repository_root(Path(schema.__file__)))
        self.schemas = self.root / schema.SCHEMAS_DIRECTORY
        self.schemas.mkdir(parents=True)
        for path in source.glob("*.json"):
            (self.schemas / path.name).write_text(path.read_text(encoding="utf-8"),
                                                  encoding="utf-8")
        (self.root / schema.RAW_DIRECTORY).mkdir()
        (self.root / schema.LEGACY_DIRECTORY).mkdir()

    def write(self, name: str, document: object, directory: str) -> Path:
        path = self.root / directory / name
        path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
        return path

    def chain(self, path: Path, source=None, target=None, apply=True) -> dict:
        return migrate.run(self.root, path, source, target, apply)

    def test_version_zero_reaches_the_newest_version(self) -> None:
        path = self.write("agent-skills-protokol-a-b-20260820T192700Z.json",
                          VERSION_ZERO, schema.LEGACY_DIRECTORY)
        found = self.chain(path)
        self.assertEqual(found["result"], "PASS")
        self.assertEqual(found["version"], 2)
        self.assertEqual(len(found["gates"]), 2)
        self.assertFalse(path.exists())
        stored = json.loads((self.root / found["target"]).read_text(encoding="utf-8"))
        self.assertEqual(schema.validate(stored, 2, self.root), [])

    def test_gaps_of_the_first_step_land_in_the_stored_file(self) -> None:
        path = self.write("agent-skills-protokol-a-b-20260820T192700Z.json",
                          VERSION_ZERO, schema.LEGACY_DIRECTORY)
        found = self.chain(path)
        stored = json.loads((self.root / found["target"]).read_text(encoding="utf-8"))
        fields = [entry["field"] for entry in stored["migration_gaps"]]
        self.assertEqual(fields, ["agent", "description", "interactions",
                                  "corrections", "finished", "uid"])

    def test_measurement_already_in_the_newest_version_is_left_alone(self) -> None:
        document = dict(VERSION_ONE, schema_version=2, uid="a" * 32, migration_gaps=[])
        path = self.write("a.json", document, schema.RAW_DIRECTORY)
        found = self.chain(path)
        self.assertEqual(found["result"], "PASS")
        self.assertEqual(found["gates"], [])
        self.assertTrue(path.exists())
        self.assertIn("jest już w wersji 2", found["notices"][0]["message"])

    def test_declared_version_that_does_not_match_the_content(self) -> None:
        path = self.write("a.json", VERSION_ONE, schema.RAW_DIRECTORY)
        found = self.chain(path, source=0)
        self.assertEqual(found["result"], "FAIL")
        self.assertIn("podano wersję 0", found["errors"][0]["message"])

    def test_chain_stops_on_the_step_that_fails(self) -> None:
        broken = dict(VERSION_ZERO)
        del broken["run_id"]
        path = self.write("a-20260820T192700Z.json", broken, schema.LEGACY_DIRECTORY)
        found = self.chain(path)
        self.assertEqual(found["result"], "FAIL")
        self.assertEqual(found["version"], 0)
        self.assertIn("stanęła na wersji 0", found["errors"][-1]["message"])
        self.assertTrue(path.exists())

    def test_missing_script_for_a_pair_of_versions(self) -> None:
        (self.schemas / "3.json").write_text(
            (self.schemas / "2.json").read_text(encoding="utf-8"), encoding="utf-8")
        document = dict(VERSION_ONE, schema_version=2, uid="a" * 32, migration_gaps=[])
        path = self.write("a.json", document, schema.RAW_DIRECTORY)
        found = self.chain(path)
        self.assertEqual(found["result"], "FAIL")
        self.assertIn("brak skryptu migracji z wersji 2 do 3",
                      found["errors"][0]["message"])

    def test_target_version_given_on_the_call(self) -> None:
        path = self.write("agent-skills-protokol-a-b-20260820T192700Z.json",
                          VERSION_ZERO, schema.LEGACY_DIRECTORY)
        found = self.chain(path, target=1)
        self.assertEqual(found["result"], "PASS")
        self.assertEqual(found["version"], 1)
        self.assertEqual(len(found["gates"]), 1)

    def test_without_apply_only_the_first_step_runs(self) -> None:
        path = self.write("agent-skills-protokol-a-b-20260820T192700Z.json",
                          VERSION_ZERO, schema.LEGACY_DIRECTORY)
        found = self.chain(path, apply=False)
        self.assertEqual(found["result"], "PASS")
        self.assertEqual(len(found["gates"]), 1)
        self.assertTrue(path.exists())
        self.assertIn("bez --apply", found["notices"][0]["message"])

    def test_file_that_does_not_exist(self) -> None:
        found = self.chain(self.root / schema.RAW_DIRECTORY / "brak.json")
        self.assertEqual(found["result"], "FAIL")
        self.assertEqual(found["errors"][0]["message"], "nie ma takiego pliku")

    def test_file_that_is_not_json(self) -> None:
        path = self.root / schema.RAW_DIRECTORY / "a.json"
        path.write_text("{", encoding="utf-8")
        found = self.chain(path)
        self.assertEqual(found["result"], "FAIL")
        self.assertIn("nie udało się odczytać", found["errors"][0]["message"])

    def test_version_field_that_is_not_an_integer(self) -> None:
        path = self.write("a.json", dict(VERSION_ONE, schema_version="2"),
                          schema.RAW_DIRECTORY)
        found = self.chain(path)
        self.assertEqual(found["result"], "FAIL")
        self.assertIn("schema_version", found["errors"][0]["message"])


if __name__ == "__main__":
    unittest.main()
