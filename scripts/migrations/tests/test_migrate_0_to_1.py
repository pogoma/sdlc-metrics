#!/usr/bin/env python3
"""Tests of the migration from version 0 to version 1."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS / "migrations"))

import migrate_0_to_1
import schema

SCRIPT = SCRIPTS / "migrations" / "migrate_0_to_1.py"

VERSION_ZERO = {
    "project": "agent-skills",
    "process": "protokol-a-b",
    "run_id": "af41ec7",
    "measurements": {"plan_questions": {"definition": "liczba pytań", "value": 2}},
}


class MigrateZeroToOneTest(unittest.TestCase):
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

    def write(self, name: str, document: object) -> Path:
        path = self.root / schema.LEGACY_DIRECTORY / name
        path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
        return path

    def call(self, path: Path, *arguments: str) -> dict:
        finished = subprocess.run(
            [sys.executable, str(SCRIPT), str(path), "--root", str(self.root)]
            + list(arguments), capture_output=True, text=True, check=False)
        return json.loads(finished.stdout)

    def stored(self, report: dict) -> dict:
        return json.loads((self.root / report["target"]).read_text(encoding="utf-8"))

    def test_measurement_becomes_version_one(self) -> None:
        path = self.write("agent-skills-protokol-a-b-20260820T192700Z.json", VERSION_ZERO)
        report = self.call(path, "--apply")
        self.assertEqual(report["result"], "PASS")
        stored = self.stored(report)
        self.assertEqual(schema.validate(stored, 1, self.root), [])
        self.assertEqual(stored["protocol"], "A-B")
        self.assertEqual(stored["name"], "protokol-a-b")
        self.assertEqual(stored["run_id"], "af41ec7")
        self.assertEqual(stored["measurements"], VERSION_ZERO["measurements"])
        self.assertFalse(path.exists())

    def test_name_follows_the_version_one_convention(self) -> None:
        path = self.write("agent-skills-protokol-a-b-20260820T192700Z.json", VERSION_ZERO)
        report = self.call(path, "--apply")
        self.assertEqual(report["target"],
                         "raw/agent-skills-A-B-20260820T192700Z.json")

    def test_stamp_comes_from_the_file_name(self) -> None:
        path = self.write("agent-skills-protokol-a-b-20260820T192700Z.json", VERSION_ZERO)
        report = self.call(path, "--apply")
        self.assertEqual(self.stored(report)["finished"], "20260820T192700Z")
        fields = [entry["field"] for entry in report["gaps"]]
        self.assertIn("finished", fields)

    def test_name_without_a_stamp(self) -> None:
        path = self.write("bez-znacznika.json", VERSION_ZERO)
        report = self.call(path, "--apply")
        self.assertEqual(report["result"], "PASS")
        self.assertNotIn("finished", self.stored(report))
        self.assertTrue(report["target"].endswith("00000000T000000Z.json"))

    def test_process_without_a_readable_protocol(self) -> None:
        path = self.write("a-20260820T192700Z.json",
                          dict(VERSION_ZERO, process="jakaś ścieżka"))
        report = self.call(path, "--apply")
        stored = self.stored(report)
        self.assertEqual(stored["protocol"], migrate_0_to_1.UNKNOWN_PROTOCOL)
        self.assertEqual(schema.validate(stored, 1, self.root), [])
        fields = [entry["field"] for entry in report["gaps"]]
        self.assertIn("protocol", fields)

    def test_every_field_that_version_zero_lacked_is_recorded(self) -> None:
        path = self.write("agent-skills-protokol-a-b-20260820T192700Z.json", VERSION_ZERO)
        report = self.call(path, "--apply")
        fields = [entry["field"] for entry in report["gaps"]]
        self.assertEqual(fields, ["agent", "description", "interactions",
                                  "corrections", "finished"])
        for entry in report["gaps"]:
            self.assertEqual(entry["from_version"], 0)

    def test_gaps_are_not_stored_because_version_one_has_no_place_for_them(self) -> None:
        path = self.write("agent-skills-protokol-a-b-20260820T192700Z.json", VERSION_ZERO)
        report = self.call(path, "--apply")
        self.assertNotIn("migration_gaps", self.stored(report))
        self.assertTrue(report["gaps"])

    def test_measurement_without_run_id(self) -> None:
        document = dict(VERSION_ZERO)
        del document["run_id"]
        path = self.write("a-20260820T192700Z.json", document)
        report = self.call(path, "--apply")
        self.assertEqual(report["result"], "FAIL")
        self.assertIn("brak pola run_id", report["errors"][0]["message"])
        self.assertTrue(path.exists())

    def test_measurement_from_raw_is_read_as_version_one(self) -> None:
        path = self.root / schema.RAW_DIRECTORY / "a.json"
        path.write_text(json.dumps(VERSION_ZERO), encoding="utf-8")
        report = self.call(path, "--apply")
        self.assertEqual(report["result"], "FAIL")
        self.assertIn("plik jest w wersji 1", report["errors"][0]["message"])

    def test_without_apply_nothing_changes(self) -> None:
        path = self.write("agent-skills-protokol-a-b-20260820T192700Z.json", VERSION_ZERO)
        report = self.call(path)
        self.assertEqual(report["result"], "PASS")
        self.assertTrue(path.exists())
        self.assertFalse((self.root / report["target"]).exists())


if __name__ == "__main__":
    unittest.main()
