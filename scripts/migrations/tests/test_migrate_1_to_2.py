#!/usr/bin/env python3
"""Tests of the migration from version 1 to version 2."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS / "migrations"))

import migration
import migrate_1_to_2
import schema

SCRIPT = SCRIPTS / "migrations" / "migrate_1_to_2.py"

VERSION_ONE = {
    "protocol": "A",
    "name": "planowanie zmiany",
    "project": "sdlc",
    "agent": {"name": "agent", "sessions": ["sesja"]},
    "description": "Przebieg próbny.",
    "interactions": 1,
    "corrections": [],
    "measurements": {"plan_questions": {"definition": "pytania", "value": 2}},
    "started": "20260101T110000Z",
    "finished": "20260101T120000Z",
    "run_id": "abc1234",
}


class MigrateOneToTwoTest(unittest.TestCase):
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

    def write(self, name: str, document: object) -> Path:
        path = self.root / schema.RAW_DIRECTORY / name
        path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
        return path

    def call(self, path: Path, *arguments: str) -> dict:
        finished = subprocess.run(
            [sys.executable, str(SCRIPT), str(path), "--root", str(self.root)]
            + list(arguments), capture_output=True, text=True, check=False)
        return json.loads(finished.stdout)

    def test_measurement_gains_the_three_new_fields(self) -> None:
        path = self.write("sdlc-A-20260101T120000Z.json", VERSION_ONE)
        report = self.call(path, "--apply")
        self.assertEqual(report["result"], "PASS")
        stored = json.loads((self.root / report["target"]).read_text(encoding="utf-8"))
        self.assertEqual(stored["schema_version"], 2)
        self.assertRegex(stored["uid"], r"^[0-9a-f]{32}$")
        self.assertEqual(len(stored["migration_gaps"]), 1)
        self.assertEqual(stored["migration_gaps"][0]["field"], "uid")

    def test_name_follows_the_new_convention(self) -> None:
        path = self.write("sdlc-A-20260101T120000Z.json", VERSION_ONE)
        report = self.call(path, "--apply")
        stored = json.loads((self.root / report["target"]).read_text(encoding="utf-8"))
        self.assertEqual(report["target"], "raw/20260101T120000Z-sdlc-{}.json".format(
            stored["uid"]))

    def test_input_disappears_and_result_fits_version_two(self) -> None:
        path = self.write("sdlc-A-20260101T120000Z.json", VERSION_ONE)
        report = self.call(path, "--apply")
        self.assertFalse(path.exists())
        stored = json.loads((self.root / report["target"]).read_text(encoding="utf-8"))
        self.assertEqual(schema.validate(stored, 2, self.root), [])

    def test_measurement_without_a_finish_stamp_records_a_gap(self) -> None:
        document = dict(VERSION_ONE)
        del document["finished"]
        del document["started"]
        path = self.write("sdlc-A-20260101T120000Z.json", document)
        report = self.call(path, "--apply")
        stored = json.loads((self.root / report["target"]).read_text(encoding="utf-8"))
        fields = [entry["field"] for entry in stored["migration_gaps"]]
        self.assertEqual(fields, ["uid", "finished"])
        self.assertTrue(report["target"].startswith("raw/20260101T120000Z-"))

    def test_carried_gaps_are_stored_before_the_ones_this_step_records(self) -> None:
        carried = self.root / "gaps.json"
        carried.write_text(json.dumps([migration.gap("agent", 0, "wersja 0 nie miała")]),
                           encoding="utf-8")
        path = self.write("sdlc-A-20260101T120000Z.json", VERSION_ONE)
        report = self.call(path, "--carry-gaps", str(carried), "--apply")
        stored = json.loads((self.root / report["target"]).read_text(encoding="utf-8"))
        fields = [entry["field"] for entry in stored["migration_gaps"]]
        self.assertEqual(fields, ["agent", "uid"])

    def test_without_apply_nothing_changes(self) -> None:
        path = self.write("sdlc-A-20260101T120000Z.json", VERSION_ONE)
        report = self.call(path)
        self.assertEqual(report["result"], "PASS")
        self.assertTrue(path.exists())
        self.assertFalse((self.root / report["target"]).exists())

    def test_measurement_already_in_version_two(self) -> None:
        path = self.write("a.json", dict(VERSION_ONE, schema_version=2,
                                         uid="a" * 32, migration_gaps=[]))
        report = self.call(path, "--apply")
        self.assertEqual(report["result"], "FAIL")
        self.assertIn("plik jest w wersji 2", report["errors"][0]["message"])

    def test_measurement_broken_in_version_one(self) -> None:
        document = dict(VERSION_ONE)
        del document["agent"]
        path = self.write("a.json", document)
        report = self.call(path, "--apply")
        self.assertEqual(report["result"], "FAIL")
        self.assertTrue(path.exists())

    def test_field_order_of_the_result(self) -> None:
        path = self.write("sdlc-A-20260101T120000Z.json", VERSION_ONE)
        report = self.call(path, "--apply")
        stored = json.loads((self.root / report["target"]).read_text(encoding="utf-8"))
        self.assertEqual(list(stored)[:2], ["schema_version", "uid"])
        self.assertEqual([key for key in migrate_1_to_2.ORDER if key in stored],
                         list(stored))


if __name__ == "__main__":
    unittest.main()
