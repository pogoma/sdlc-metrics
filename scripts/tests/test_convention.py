#!/usr/bin/env python3
"""Tests of the loading of the libraries of the Python convention."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import convention


class ConventionTest(unittest.TestCase):

    def test_libraries_are_found_next_to_the_metrics(self) -> None:
        found = convention.package_path()
        self.assertIsNotNone(found)
        self.assertTrue((found / "json_schema").is_dir())

    def test_metrics_outside_a_developer_repository_find_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            self.assertIsNone(convention.package_path(Path(directory) / "skrypt.py"))

    def test_validator_and_yaml_come_from_one_load(self) -> None:
        validator = convention.validator()
        self.assertIs(convention.validator(), validator)
        self.assertEqual(convention.yaml().load("a: 1\n"), {"a": 1})
        self.assertEqual(validator.validate({"a": 1}, {"required": ["a"]}), [])

    def test_libraries_do_not_take_over_the_name_libs(self) -> None:
        convention.validator()
        self.assertNotIn("libs.json_schema", sys.modules)


if __name__ == "__main__":
    unittest.main()
