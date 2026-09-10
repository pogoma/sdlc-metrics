#!/usr/bin/env python3
"""Tests of the gate over stored measurements."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import schema
import validate

MEASUREMENT = {
    "protocol": "A",
    "name": "planowanie zmiany",
    "project": "sdlc",
    "agent": {"name": "agent", "sessions": ["sesja"]},
    "description": "Przebieg próbny.",
    "interactions": 1,
    "corrections": [],
    "measurements": {"plan_questions": {"definition": "pytania", "value": 2}},
}


class ValidateTest(unittest.TestCase):
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

    def write(self, name: str, document: object,
              directory: str = schema.RAW_DIRECTORY) -> Path:
        place = self.root / directory
        place.mkdir(parents=True, exist_ok=True)
        path = place / name
        text = document if isinstance(document, str) else json.dumps(document)
        path.write_text(text, encoding="utf-8")
        return path

    def run_gate(self, *arguments: str) -> dict:
        return validate.run(self.root, list(arguments))

    def test_directory_that_fits(self) -> None:
        self.write("a.json", MEASUREMENT)
        self.write("b.json", MEASUREMENT)
        self.assertEqual(self.run_gate()["result"], "PASS")

    def test_file_that_does_not_fit_its_version(self) -> None:
        broken = dict(MEASUREMENT)
        del broken["interactions"]
        self.write("a.json", broken)
        found = self.run_gate()
        self.assertEqual(found["result"], "FAIL")
        self.assertIn("brak pola interactions", found["errors"][0]["message"])
        self.assertEqual(found["errors"][0]["subject"], "raw/a.json")

    def test_version_without_a_schema(self) -> None:
        self.write("a.json", dict(MEASUREMENT, schema_version=9))
        found = self.run_gate()
        self.assertEqual(found["result"], "FAIL")
        self.assertEqual(found["errors"][0]["message"], "brak schematu wersji 9")

    def test_version_field_that_is_not_an_integer(self) -> None:
        self.write("a.json", dict(MEASUREMENT, schema_version="2"))
        found = self.run_gate()
        self.assertEqual(found["result"], "FAIL")
        self.assertIn("schema_version", found["errors"][0]["message"])

    def test_file_that_is_not_json(self) -> None:
        self.write("a.json", "{")
        found = self.run_gate()
        self.assertEqual(found["result"], "FAIL")
        self.assertIn("nie jest poprawnym JSON-em", found["errors"][0]["message"])

    def test_file_with_another_suffix(self) -> None:
        self.write("a.txt", MEASUREMENT)
        found = self.run_gate()
        self.assertEqual(found["result"], "FAIL")
        self.assertIn("osobny plik .json", found["errors"][0]["message"])

    def test_single_file_named_on_the_call(self) -> None:
        path = self.write("a.json", MEASUREMENT)
        self.write("b.json", {"cokolwiek": 1})
        self.assertEqual(self.run_gate(str(path))["result"], "PASS")

    def test_file_that_does_not_exist(self) -> None:
        found = self.run_gate(str(self.root / "raw" / "brak.json"))
        self.assertEqual(found["result"], "FAIL")
        self.assertEqual(found["errors"][0]["message"], "nie ma takiego pliku")

    def test_empty_directory_is_a_notice_not_an_error(self) -> None:
        found = self.run_gate()
        self.assertEqual(found["result"], "PASS")
        self.assertEqual(found["counts"]["notices"], 1)

    def test_legacy_file_is_read_as_version_zero(self) -> None:
        path = self.write("a.json", {"project": "sdlc", "process": "protokol-a-b",
                                     "run_id": "abc1234", "measurements": {}},
                          schema.LEGACY_DIRECTORY)
        self.assertEqual(self.run_gate(str(path))["result"], "PASS")

    def test_measurement_of_version_two(self) -> None:
        document = dict(MEASUREMENT, schema_version=2, uid="0" * 32, migration_gaps=[])
        self.write("a.json", document)
        self.assertEqual(self.run_gate()["result"], "PASS")

    def test_measurement_of_version_two_without_uid(self) -> None:
        document = dict(MEASUREMENT, schema_version=2, migration_gaps=[])
        self.write("a.json", document)
        found = self.run_gate()
        self.assertEqual(found["result"], "FAIL")
        self.assertIn("brak pola uid", found["errors"][0]["message"])


if __name__ == "__main__":
    unittest.main()
