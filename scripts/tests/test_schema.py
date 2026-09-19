#!/usr/bin/env python3
"""Tests of the schema checker."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import schema

# Schemas and measurements live in the directory of their kind (SDLC-0030).
SCHEMAS = "{}/{}".format(schema.SCHEMAS_DIRECTORY, schema.PROCESS_KIND)
RAW = "{}/{}".format(schema.RAW_DIRECTORY, schema.PROCESS_KIND)


def write(root: Path, version: int, document: dict) -> None:
    place = root / SCHEMAS
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
        return schema.validate(document, version, self.root, schema.PROCESS_KIND)

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
        self.assertEqual(schema.versions(schema.PROCESS_KIND, self.root), [1, 2])
        self.assertEqual(schema.latest(schema.PROCESS_KIND, self.root), 2)

    def test_latest_without_any_schema(self) -> None:
        with tempfile.TemporaryDirectory() as empty:
            with self.assertRaises(ValueError):
                schema.latest(Path(empty))

    def test_version_from_the_field(self) -> None:
        self.assertEqual(schema.version_of({"schema_version": 2}), 2)

    def test_version_from_the_directory(self) -> None:
        raw = self.root / RAW / "a.json"
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
        for name, version in ((RAW, 1), (schema.LEGACY_DIRECTORY, 0)):
            for path in sorted((root / name).glob("*.json")):
                document = json.loads(path.read_text(encoding="utf-8"))
                found = schema.validate(document, schema.version_of(document, path), root,
                                        schema.PROCESS_KIND)
                self.assertEqual(found, [], "{}: {}".format(path.name, found))


class KindTest(unittest.TestCase):
    """Choosing the schema by the pair of kind and version (SDLC-0030)."""

    def setUp(self) -> None:
        self.place = tempfile.TemporaryDirectory()
        self.root = Path(self.place.name)
        self.addCleanup(self.place.cleanup)
        for kind in (schema.PROCESS_KIND, schema.PERFORMANCE_KIND):
            place = self.root / schema.SCHEMAS_DIRECTORY / kind
            place.mkdir(parents=True)
            (place / "1.json").write_text(json.dumps(SIMPLE, ensure_ascii=False),
                                          encoding="utf-8")

    def test_kinds_are_the_directories_of_schemas(self) -> None:
        self.assertEqual(schema.kinds(self.root),
                         [schema.PERFORMANCE_KIND, schema.PROCESS_KIND])

    def test_kind_from_the_field(self) -> None:
        self.assertEqual(
            schema.kind_of({"kind": schema.PERFORMANCE_KIND}, None, self.root),
            schema.PERFORMANCE_KIND)

    def test_kind_from_the_directory(self) -> None:
        path = self.root / schema.RAW_DIRECTORY / schema.PERFORMANCE_KIND / "a.json"
        self.assertEqual(schema.kind_of({}, path, self.root), schema.PERFORMANCE_KIND)

    def test_measurement_without_a_kind_is_a_protocol_run(self) -> None:
        self.assertEqual(schema.kind_of({}, None, self.root), schema.PROCESS_KIND)

    def test_unknown_kind_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            schema.kind_of({"kind": "wymyslony"}, None, self.root)

    def test_kind_field_that_is_not_a_name(self) -> None:
        with self.assertRaises(ValueError):
            schema.kind_of({"kind": 7}, None, self.root)

    def test_each_kind_keeps_its_own_versions(self) -> None:
        place = self.root / schema.SCHEMAS_DIRECTORY / schema.PERFORMANCE_KIND
        (place / "2.json").write_text(json.dumps(SIMPLE, ensure_ascii=False),
                                      encoding="utf-8")
        self.assertEqual(schema.versions(schema.PROCESS_KIND, self.root), [1])
        self.assertEqual(schema.versions(schema.PERFORMANCE_KIND, self.root), [1, 2])


class PerformanceSchemaTest(unittest.TestCase):
    """The schema of the performance measurement, as it lies in the repository."""

    MEASUREMENT = {
        "schema_version": 1,
        "kind": schema.PERFORMANCE_KIND,
        "uid": "0" * 32,
        "project": "sdlc",
        "finished": "20260919T140000Z",
        "commands": [{
            "file": "scripts/check.py",
            "name": "check",
            "arguments": [],
            "repetitions": 2,
            "runs": [
                {"duration_ms": 16500.0, "outcome": "ok",
                 "spans": [{"operation": "uruchomienie weryfikacji",
                            "duration_ms": 1400.0,
                            "span_id": "a" * 16, "parent_span_id": "b" * 16}]},
                {"duration_ms": 16100.5, "outcome": "ok", "spans": []},
            ],
        }],
        "environment": {"system": "Linux", "release": "7.0.0", "machine": "x86_64",
                        "python": "3.12.0", "cpu_count": 8, "load_average": 0.4},
        "migration_gaps": [],
    }

    def setUp(self) -> None:
        self.root = schema.repository_root(Path(schema.__file__))

    def problems(self, document: dict) -> list:
        return schema.validate(document, 1, self.root, schema.PERFORMANCE_KIND)

    def changed(self, **values) -> dict:
        document = json.loads(json.dumps(self.MEASUREMENT))
        document.update(values)
        return document

    def test_measurement_that_fits(self) -> None:
        self.assertEqual(self.problems(self.MEASUREMENT), [])

    def test_measurement_without_commands(self) -> None:
        self.assertEqual(self.problems(self.changed(commands=[])),
                         ["pomiar.commands ma mniej niż 1 elementów"])

    def test_outcome_outside_the_dictionary(self) -> None:
        document = json.loads(json.dumps(self.MEASUREMENT))
        document["commands"][0]["runs"][0]["outcome"] = "moze"
        self.assertTrue(any("outcome" in problem for problem in self.problems(document)))

    def test_environment_without_the_machine(self) -> None:
        environment = dict(self.MEASUREMENT["environment"])
        del environment["cpu_count"]
        self.assertTrue(any("cpu_count" in problem
                            for problem in self.problems(self.changed(environment=environment))))

    def test_optional_fields_of_the_environment_may_be_absent(self) -> None:
        environment = {"system": "Linux", "release": "7.0.0", "machine": "x86_64",
                       "python": "3.12.0", "cpu_count": 8}
        self.assertEqual(self.problems(self.changed(environment=environment)), [])

    def test_kind_of_another_measurement_is_refused(self) -> None:
        self.assertTrue(any("kind" in problem
                            for problem in self.problems(self.changed(kind="process"))))


if __name__ == "__main__":
    unittest.main()
