#!/usr/bin/env python3
"""Tests of the schema checker."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import schema


def write(root: Path, version: int, document: dict) -> None:
    place = root / schema.SCHEMAS_DIRECTORY
    place.mkdir(parents=True, exist_ok=True)
    (place / "{}.json".format(version)).write_text(
        json.dumps(document, ensure_ascii=False), encoding="utf-8")


SIMPLE = {
    "type": "object",
    "additionalProperties": False,
    "required": ["name", "count"],
    "properties": {
        "name": {"$ref": "#/$defs/name"},
        "count": {"type": "integer", "minimum": 0, "maximum": 10},
        "kind": {"type": "string", "enum": ["a", "b"]},
        "items": {"type": "array", "minItems": 1, "items": {"type": "string"}},
    },
    "$defs": {
        "name": {"type": "string", "minLength": 2, "maxLength": 5, "pattern": "\\S"},
    },
}


class SchemaTest(unittest.TestCase):
    def setUp(self) -> None:
        self.place = tempfile.TemporaryDirectory()
        self.root = Path(self.place.name)
        write(self.root, 1, SIMPLE)
        self.addCleanup(self.place.cleanup)

    def problems(self, document: object, version: int = 1) -> list:
        return schema.validate(document, version, self.root)

    def test_document_that_fits_has_no_problems(self) -> None:
        self.assertEqual(self.problems({"name": "abc", "count": 3}), [])

    def test_missing_required_field(self) -> None:
        found = self.problems({"name": "abc"})
        self.assertEqual(found, ["pomiar: brak pola count"])

    def test_property_outside_the_schema(self) -> None:
        found = self.problems({"name": "abc", "count": 1, "extra": 1})
        self.assertIn("pomiar: pole spoza schematu: extra", found)

    def test_wrong_type(self) -> None:
        found = self.problems({"name": "abc", "count": "trzy"})
        self.assertIn("pomiar.count nie jest liczbą całkowitą", found)

    def test_boolean_is_not_an_integer(self) -> None:
        found = self.problems({"name": "abc", "count": True})
        self.assertIn("pomiar.count nie jest liczbą całkowitą", found)

    def test_pattern_and_length_come_from_the_reference(self) -> None:
        found = self.problems({"name": "   ", "count": 1})
        self.assertIn("pomiar.name nie pasuje do wzorca \\S", found)
        found = self.problems({"name": "a", "count": 1})
        self.assertIn("pomiar.name jest krótsze niż 2 znaków", found)
        found = self.problems({"name": "abcdef", "count": 1})
        self.assertIn("pomiar.name ma 6 znaków, limit to 5", found)

    def test_minimum_and_maximum(self) -> None:
        self.assertIn("pomiar.count jest mniejsze niż 0",
                      self.problems({"name": "abc", "count": -1}))
        self.assertIn("pomiar.count jest większe niż 10",
                      self.problems({"name": "abc", "count": 11}))

    def test_enum(self) -> None:
        found = self.problems({"name": "abc", "count": 1, "kind": "c"})
        self.assertIn("pomiar.kind ma wartość spoza listy dopuszczonych: a, b", found)

    def test_min_items_and_item_schema(self) -> None:
        self.assertIn("pomiar.items ma mniej niż 1 elementów",
                      self.problems({"name": "abc", "count": 1, "items": []}))
        self.assertIn("pomiar.items[0] nie jest tekstem",
                      self.problems({"name": "abc", "count": 1, "items": [1]}))

    def test_keyword_outside_the_subset_is_a_problem(self) -> None:
        write(self.root, 2, {"type": "object", "propertyNames": {"type": "string"}})
        found = self.problems({}, 2)
        self.assertEqual(
            found, ["schemat pola pomiar: słowo kluczowe spoza podzbioru: propertyNames"])

    def test_reference_that_leads_nowhere(self) -> None:
        write(self.root, 2, {"$ref": "#/$defs/absent", "$defs": {}})
        self.assertEqual(self.problems({}, 2), ["schemat pola pomiar: brak definicji absent"])
        write(self.root, 3, {"$ref": "gdzie indziej"})
        self.assertEqual(self.problems({}, 3), [
            "schemat pola pomiar: $ref gdzie indziej nie wskazuje definicji w tym schemacie"])

    def test_additional_properties_as_a_schema(self) -> None:
        write(self.root, 2, {"type": "object",
                             "additionalProperties": {"type": "integer"}})
        self.assertEqual(self.problems({"a": 1}, 2), [])
        self.assertEqual(self.problems({"a": "x"}, 2), ["pomiar.a nie jest liczbą całkowitą"])

    def test_missing_schema_of_a_version(self) -> None:
        with self.assertRaises(ValueError):
            self.problems({}, 9)

    def test_versions_and_latest(self) -> None:
        write(self.root, 2, SIMPLE)
        self.assertEqual(schema.versions(self.root), [1, 2])
        self.assertEqual(schema.latest(self.root), 2)

    def test_latest_without_any_schema(self) -> None:
        with tempfile.TemporaryDirectory() as empty:
            with self.assertRaises(ValueError):
                schema.latest(Path(empty))

    def test_version_from_the_field(self) -> None:
        self.assertEqual(schema.version_of({"schema_version": 2}), 2)

    def test_version_from_the_directory(self) -> None:
        raw = self.root / schema.RAW_DIRECTORY / "a.json"
        legacy = self.root / schema.LEGACY_DIRECTORY / "a.json"
        self.assertEqual(schema.version_of({}, raw), 1)
        self.assertEqual(schema.version_of({}, legacy), 0)
        self.assertEqual(schema.version_of({}), 1)

    def test_version_field_that_is_not_an_integer(self) -> None:
        with self.assertRaises(ValueError):
            schema.version_of({"schema_version": "2"})
        with self.assertRaises(ValueError):
            schema.version_of({"schema_version": True})

    def test_stored_schemas_accept_the_measurements_in_the_repository(self) -> None:
        root = schema.repository_root(Path(schema.__file__))
        for name, version in ((schema.RAW_DIRECTORY, 1), (schema.LEGACY_DIRECTORY, 0)):
            for path in sorted((root / name).glob("*.json")):
                document = json.loads(path.read_text(encoding="utf-8"))
                found = schema.validate(document, schema.version_of(document, path), root)
                self.assertEqual(found, [], "{}: {}".format(path.name, found))


if __name__ == "__main__":
    unittest.main()
