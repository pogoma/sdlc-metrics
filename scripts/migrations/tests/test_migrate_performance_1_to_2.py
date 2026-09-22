#!/usr/bin/env python3
"""Tests of the migration of a performance measurement from version 1 to version 2."""

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SCRIPTS))

import convention
import kinds

SCRIPT = SCRIPTS / "migrations" / "migrate_performance_1_to_2.py"
ROOT = kinds.repository_root(Path(kinds.__file__))


def stored_measurement() -> Path:
    """A performance measurement of version 1 as it lies in the repository."""
    place = ROOT / kinds.RAW_DIRECTORY / kinds.PERFORMANCE_KIND
    for path in sorted(place.glob("*.json")):
        return path
    raise unittest.SkipTest("w repozytorium nie ma pomiaru wydajności w wersji 1")


class MigratePerformanceOneToTwoTest(unittest.TestCase):
    def setUp(self) -> None:
        self.place = tempfile.TemporaryDirectory()
        self.root = Path(self.place.name)
        self.addCleanup(self.place.cleanup)
        shutil.copytree(ROOT / kinds.SCHEMAS_DIRECTORY, self.root / kinds.SCHEMAS_DIRECTORY)
        raw = self.root / kinds.RAW_DIRECTORY / kinds.PERFORMANCE_KIND
        raw.mkdir(parents=True)
        self.source = stored_measurement()
        self.path = raw / self.source.name
        shutil.copy(self.source, self.path)

    def call(self, *arguments: str) -> dict:
        finished = subprocess.run(
            [sys.executable, str(SCRIPT), str(self.path), "--root", str(self.root)]
            + list(arguments), capture_output=True, text=True, check=False)
        return json.loads(finished.stdout)

    def test_content_moves_to_a_yaml_file_of_version_two(self) -> None:
        before = kinds.read(self.path)
        report = self.call("--apply")
        self.assertEqual(report["result"], "PASS", report)
        self.assertEqual(report["target"],
                         "raw/performance/{}.yaml".format(self.source.stem))
        stored = convention.yaml().load(
            (self.root / report["target"]).read_text(encoding="utf-8"))
        self.assertEqual(stored, dict(before, schema_version=2))
        self.assertEqual(kinds.validate(stored, 2, self.root, kinds.PERFORMANCE_KIND), [])
        self.assertFalse(self.path.exists())

    def test_no_gap_is_recorded(self) -> None:
        self.assertEqual(self.call("--apply")["gaps"], [])


if __name__ == "__main__":
    unittest.main()
