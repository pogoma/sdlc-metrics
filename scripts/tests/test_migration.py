#!/usr/bin/env python3
"""Tests of the machinery shared by every migration step."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import migration
import schema

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


def to_two(document, gaps, path):
    result = dict(document)
    result["schema_version"] = 2
    result["uid"] = migration.new_uid()
    result["migration_gaps"] = list(gaps)
    return result


def name_of(document, path):
    return "{}-{}-{}.json".format(document.get("finished"), document.get("project"),
                                  document.get("uid"))


class MigrationTest(unittest.TestCase):
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
        self.uid = migration.new_uid
        migration.new_uid = lambda: "a" * 32
        self.addCleanup(setattr, migration, "new_uid", self.uid)

    def write(self, name, document, directory=schema.RAW_DIRECTORY):
        place = self.root / directory
        place.mkdir(parents=True, exist_ok=True)
        path = place / name
        text = document if isinstance(document, str) else json.dumps(document)
        path.write_text(text, encoding="utf-8")
        return path

    def step(self, path, apply=True, carried=None, transform=to_two, source=1):
        return migration.migrate(self.root, path, source, 2, transform, name_of,
                                 carried or [], apply)

    def test_file_that_fits_becomes_the_next_version(self) -> None:
        path = self.write("sdlc-A-20260101T120000Z.json", VERSION_ONE)
        report = self.step(path)
        self.assertEqual(report.as_document()["result"], "PASS")
        self.assertFalse(path.exists())
        target = self.root / report.target
        self.assertTrue(target.exists())
        stored = json.loads(target.read_text(encoding="utf-8"))
        self.assertEqual(stored["schema_version"], 2)
        self.assertEqual(stored["uid"], "a" * 32)

    def test_without_apply_nothing_changes(self) -> None:
        path = self.write("sdlc-A-20260101T120000Z.json", VERSION_ONE)
        report = self.step(path, apply=False)
        self.assertEqual(report.as_document()["result"], "PASS")
        self.assertTrue(path.exists())
        self.assertFalse((self.root / report.target).exists())
        self.assertEqual(report.as_document()["counts"]["notices"], 1)

    def test_version_other_than_the_one_the_step_starts_from(self) -> None:
        path = self.write("a.json", dict(VERSION_ONE, schema_version=2,
                                         uid="b" * 32, migration_gaps=[]))
        report = self.step(path)
        self.assertEqual(report.as_document()["result"], "FAIL")
        self.assertIn("plik jest w wersji 2", report.errors[0]["message"])
        self.assertTrue(path.exists())

    def test_file_that_does_not_fit_its_own_version_is_left_alone(self) -> None:
        broken = dict(VERSION_ONE)
        del broken["interactions"]
        path = self.write("a.json", broken)
        report = self.step(path)
        self.assertEqual(report.as_document()["result"], "FAIL")
        self.assertTrue(path.exists())
        self.assertIn("wersja 1: pomiar: brak pola interactions",
                      report.errors[0]["message"])

    def test_result_that_does_not_fit_goes_to_damaged(self) -> None:
        def bad(document, gaps, path):
            result = to_two(document, gaps, path)
            del result["interactions"]
            return result

        path = self.write("a.json", VERSION_ONE)
        report = self.step(path, transform=bad)
        self.assertEqual(report.as_document()["result"], "FAIL")
        self.assertFalse(path.exists())
        self.assertTrue((self.root / report.target).exists())
        self.assertTrue(report.target.startswith(migration.DAMAGED_DIRECTORY))

    def test_name_that_is_already_taken(self) -> None:
        self.write("20260101T120000Z-sdlc-{}.json".format("a" * 32), VERSION_ONE)
        path = self.write("a.json", VERSION_ONE)
        report = self.step(path)
        self.assertEqual(report.as_document()["result"], "FAIL")
        self.assertIn("już istnieje", report.errors[0]["message"])
        self.assertTrue(path.exists())

    def test_carried_gaps_land_in_the_result(self) -> None:
        carried = [migration.gap("agent", 0, "wersja 0 nie miała agenta")]
        path = self.write("a.json", VERSION_ONE)
        report = self.step(path, carried=carried)
        stored = json.loads((self.root / report.target).read_text(encoding="utf-8"))
        self.assertEqual(stored["migration_gaps"], carried)
        self.assertEqual(report.as_document()["gaps"], carried)

    def test_file_that_is_not_json(self) -> None:
        path = self.write("a.json", "{")
        report = self.step(path)
        self.assertEqual(report.as_document()["result"], "FAIL")
        self.assertIn("nie jest poprawnym JSON-em", report.errors[0]["message"])

    def test_file_that_is_not_an_object(self) -> None:
        path = self.write("a.json", [1, 2])
        report = self.step(path)
        self.assertIn("pomiar nie jest obiektem", report.errors[0]["message"])

    def test_file_that_cannot_be_read(self) -> None:
        report = self.step(self.root / schema.RAW_DIRECTORY / "brak.json")
        self.assertEqual(report.as_document()["result"], "FAIL")
        self.assertIn("nie udało się odczytać", report.errors[0]["message"])

    def test_stamp_from_the_content_and_from_the_name(self) -> None:
        path = Path("sdlc-A-20260101T120000Z.json")
        self.assertEqual(migration.stamp_of({"finished": "20250505T010203Z"}, path),
                         "20250505T010203Z")
        self.assertEqual(migration.stamp_of({"started": "20250505T010203Z"}, path),
                         "20250505T010203Z")
        self.assertEqual(migration.stamp_of({}, path), "20260101T120000Z")
        self.assertIsNone(migration.stamp_of({}, Path("bez-znacznika.json")))

    def test_carried_gaps_read_from_a_file(self) -> None:
        report = migration.Report("metrics:migrate:1-2")
        path = self.root / "gaps.json"
        path.write_text(json.dumps([migration.gap("agent", 0, "brak")]),
                        encoding="utf-8")
        self.assertEqual(len(migration.read_carried(str(path), report)), 1)
        self.assertEqual(report.errors, [])

    def test_carried_gaps_that_cannot_be_read(self) -> None:
        report = migration.Report("metrics:migrate:1-2")
        migration.read_carried(str(self.root / "brak.json"), report)
        self.assertEqual(len(report.errors), 1)
        report = migration.Report("metrics:migrate:1-2")
        path = self.root / "gaps.json"
        path.write_text(json.dumps({"a": 1}), encoding="utf-8")
        migration.read_carried(str(path), report)
        self.assertIn("nie zawiera listy braków", report.errors[0]["message"])

    def test_uid_is_thirty_two_hexadecimal_characters(self) -> None:
        value = self.uid()
        self.assertEqual(len(value), 32)
        self.assertTrue(all(letter in "0123456789abcdef" for letter in value))


if __name__ == "__main__":
    unittest.main()
