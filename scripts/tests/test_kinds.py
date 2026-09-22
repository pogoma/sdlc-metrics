#!/usr/bin/env python3
"""Tests of kinds, versions and schemas of measurements."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import convention
import kinds

# Schemas and measurements live in the directory of their kind (SDLC-0030).
SCHEMAS = "{}/{}".format(kinds.SCHEMAS_DIRECTORY, kinds.PROCESS_KIND)
RAW = "{}/{}".format(kinds.RAW_DIRECTORY, kinds.PROCESS_KIND)


def write(root: Path, version: int, document: dict) -> None:
    place = root / SCHEMAS
    place.mkdir(parents=True, exist_ok=True)
    (place / "{}.yaml".format(version)).write_text(
        convention.yaml().dump(document), encoding="utf-8")


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
        return kinds.validate(document, version, self.root, kinds.PROCESS_KIND)

    def test_document_that_fits_has_no_problems(self) -> None:
        self.assertEqual(self.problems({"name": "abc", "count": 3}), [])

    def test_missing_required_field(self) -> None:
        found = self.problems({"name": "abc"})
        self.assertEqual(found, ["pomiar: brak wymaganego pola count"])

    def test_problem_names_its_place(self) -> None:
        found = self.problems({"name": "abc", "count": "trzy"})
        self.assertEqual(len(found), 1)
        self.assertTrue(found[0].startswith("pomiar/count: "))

    def test_every_problem_is_reported(self) -> None:
        found = self.problems({"name": "a", "count": 11, "extra": 1})
        self.assertEqual(len(found), 3)

    def test_keyword_of_2020_12_beyond_the_old_subset(self) -> None:
        write(self.root, 2, {"type": "object", "propertyNames": {"pattern": "^[a-z]+$"}})
        self.assertEqual(self.problems({"abc": 1}, 2), [])
        self.assertEqual(len(self.problems({"ABC": 1}, 2)), 1)

    def test_schema_that_cannot_be_compiled_is_an_error(self) -> None:
        write(self.root, 2, {"$ref": "#/$defs/absent", "$defs": {}})
        with self.assertRaises(ValueError):
            self.problems({}, 2)

    def test_schema_file_in_json_is_not_a_version(self) -> None:
        place = self.root / SCHEMAS
        (place / "2.json").write_text(json.dumps(SIMPLE), encoding="utf-8")
        self.assertEqual(kinds.versions(kinds.PROCESS_KIND, self.root), [1])

    def test_missing_schema_of_a_version(self) -> None:
        with self.assertRaises(ValueError):
            self.problems({}, 9)

    def test_versions_and_latest(self) -> None:
        write(self.root, 2, SIMPLE)
        self.assertEqual(kinds.versions(kinds.PROCESS_KIND, self.root), [1, 2])
        self.assertEqual(kinds.latest(kinds.PROCESS_KIND, self.root), 2)

    def test_latest_without_any_schema(self) -> None:
        with tempfile.TemporaryDirectory() as empty:
            with self.assertRaises(ValueError):
                kinds.latest(Path(empty))

    def test_version_from_the_field(self) -> None:
        self.assertEqual(kinds.version_of({"schema_version": 2}), 2)

    def test_version_from_the_directory(self) -> None:
        raw = self.root / RAW / "a.json"
        legacy = self.root / kinds.LEGACY_DIRECTORY / "a.json"
        self.assertEqual(kinds.version_of({}, raw), 1)
        self.assertEqual(kinds.version_of({}, legacy), 0)
        self.assertEqual(kinds.version_of({}), 1)

    def test_version_field_that_is_not_an_integer(self) -> None:
        with self.assertRaises(ValueError):
            kinds.version_of({"schema_version": "2"})
        with self.assertRaises(ValueError):
            kinds.version_of({"schema_version": True})

    def test_stored_schemas_accept_the_measurements_in_the_repository(self) -> None:
        root = kinds.repository_root(Path(kinds.__file__))
        for name, version in ((RAW, 1), (kinds.LEGACY_DIRECTORY, 0)):
            for path in sorted((root / name).glob("*.*")):
                document = kinds.read(path)
                found = kinds.validate(document, kinds.version_of(document, path), root,
                                        kinds.PROCESS_KIND)
                self.assertEqual(found, [], "{}: {}".format(path.name, found))


class SuffixTest(unittest.TestCase):
    """Format of a measurement file follows its kind and version (SDLC-0042)."""

    def test_older_versions_stay_json(self) -> None:
        self.assertEqual(kinds.suffix_for(kinds.PROCESS_KIND, 2), ".json")
        self.assertEqual(kinds.suffix_for(kinds.PERFORMANCE_KIND, 1), ".json")

    def test_newer_versions_are_yaml(self) -> None:
        self.assertEqual(kinds.suffix_for(kinds.PROCESS_KIND, 3), ".yaml")
        self.assertEqual(kinds.suffix_for(kinds.PERFORMANCE_KIND, 2), ".yaml")

    def test_newest_versions_in_the_repository_are_yaml(self) -> None:
        root = kinds.repository_root(Path(kinds.__file__))
        for kind in kinds.kinds(root):
            self.assertEqual(kinds.suffix_for(kind, kinds.latest(kind, root)), ".yaml")


class KindTest(unittest.TestCase):
    """Choosing the schema by the pair of kind and version (SDLC-0030)."""

    def setUp(self) -> None:
        self.place = tempfile.TemporaryDirectory()
        self.root = Path(self.place.name)
        self.addCleanup(self.place.cleanup)
        for kind in (kinds.PROCESS_KIND, kinds.PERFORMANCE_KIND):
            place = self.root / kinds.SCHEMAS_DIRECTORY / kind
            place.mkdir(parents=True)
            (place / "1.yaml").write_text(convention.yaml().dump(SIMPLE),
                                          encoding="utf-8")

    def test_kinds_are_the_directories_of_schemas(self) -> None:
        self.assertEqual(kinds.kinds(self.root),
                         [kinds.PERFORMANCE_KIND, kinds.PROCESS_KIND])

    def test_kind_from_the_field(self) -> None:
        self.assertEqual(
            kinds.kind_of({"kind": kinds.PERFORMANCE_KIND}, None, self.root),
            kinds.PERFORMANCE_KIND)

    def test_kind_from_the_directory(self) -> None:
        path = self.root / kinds.RAW_DIRECTORY / kinds.PERFORMANCE_KIND / "a.json"
        self.assertEqual(kinds.kind_of({}, path, self.root), kinds.PERFORMANCE_KIND)

    def test_measurement_without_a_kind_is_a_protocol_run(self) -> None:
        self.assertEqual(kinds.kind_of({}, None, self.root), kinds.PROCESS_KIND)

    def test_unknown_kind_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            kinds.kind_of({"kind": "wymyslony"}, None, self.root)

    def test_kind_field_that_is_not_a_name(self) -> None:
        with self.assertRaises(ValueError):
            kinds.kind_of({"kind": 7}, None, self.root)

    def test_each_kind_keeps_its_own_versions(self) -> None:
        place = self.root / kinds.SCHEMAS_DIRECTORY / kinds.PERFORMANCE_KIND
        (place / "2.yaml").write_text(convention.yaml().dump(SIMPLE),
                                      encoding="utf-8")
        self.assertEqual(kinds.versions(kinds.PROCESS_KIND, self.root), [1])
        self.assertEqual(kinds.versions(kinds.PERFORMANCE_KIND, self.root), [1, 2])


class PerformanceSchemaTest(unittest.TestCase):
    """The schema of the performance measurement, as it lies in the repository."""

    MEASUREMENT = {
        "schema_version": 1,
        "kind": kinds.PERFORMANCE_KIND,
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
        self.root = kinds.repository_root(Path(kinds.__file__))

    def problems(self, document: dict) -> list:
        return kinds.validate(document, 1, self.root, kinds.PERFORMANCE_KIND)

    def changed(self, **values) -> dict:
        document = json.loads(json.dumps(self.MEASUREMENT))
        document.update(values)
        return document

    def test_measurement_that_fits(self) -> None:
        self.assertEqual(self.problems(self.MEASUREMENT), [])

    def test_measurement_without_commands(self) -> None:
        found = self.problems(self.changed(commands=[]))
        self.assertEqual(len(found), 1)
        self.assertTrue(found[0].startswith("pomiar/commands: "))

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
