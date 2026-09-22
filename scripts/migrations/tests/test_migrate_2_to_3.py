#!/usr/bin/env python3
"""Tests of the migration from version 2 to version 3."""

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS / "migrations"))

import convention
import kinds
import migrate_2_to_3

SCRIPT = SCRIPTS / "migrations" / "migrate_2_to_3.py"
ROOT = kinds.repository_root(Path(kinds.__file__))


def stored_measurement() -> Path:
    """A measurement of version 2 as it lies in the repository."""
    for path in sorted((ROOT / kinds.RAW_DIRECTORY / kinds.PROCESS_KIND).glob("*.json"),
                       reverse=True):
        if kinds.version_of(kinds.read(path), path) == 2:
            return path
    raise unittest.SkipTest("w repozytorium nie ma pomiaru w wersji 2")


class MigrateTwoToThreeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.place = tempfile.TemporaryDirectory()
        self.root = Path(self.place.name)
        self.addCleanup(self.place.cleanup)
        shutil.copytree(ROOT / kinds.SCHEMAS_DIRECTORY, self.root / kinds.SCHEMAS_DIRECTORY)
        self.raw = self.root / kinds.RAW_DIRECTORY / kinds.PROCESS_KIND
        self.raw.mkdir(parents=True)
        self.source = stored_measurement()
        self.path = self.raw / self.source.name
        shutil.copy(self.source, self.path)

    def call(self, *arguments: str) -> dict:
        finished = subprocess.run(
            [sys.executable, str(SCRIPT), str(self.path), "--root", str(self.root)]
            + list(arguments), capture_output=True, text=True, check=False)
        return json.loads(finished.stdout)

    def stored(self, report: dict) -> dict:
        return convention.yaml().load(
            (self.root / report["target"]).read_text(encoding="utf-8"))

    def test_agent_becomes_a_list_with_an_unknown_model(self) -> None:
        before = kinds.read(self.path)
        report = self.call("--apply")
        self.assertEqual(report["result"], "PASS", report)
        stored = self.stored(report)
        self.assertNotIn("agent", stored)
        self.assertEqual(stored["agents"], [{"name": before["agent"]["name"],
                                             "model": migrate_2_to_3.UNKNOWN_MODEL,
                                             "sessions": before["agent"]["sessions"]}])

    def test_missing_model_is_a_gap(self) -> None:
        stored = self.stored(self.call("--apply"))
        self.assertEqual(stored["migration_gaps"][-1]["field"], "agents.model")
        self.assertEqual(stored["migration_gaps"][-1]["from_version"], 2)

    def test_result_is_a_yaml_file_that_fits_version_three(self) -> None:
        report = self.call("--apply")
        self.assertEqual(report["target"], "raw/process/{}.yaml".format(self.source.stem))
        self.assertFalse(self.path.exists())
        self.assertEqual(kinds.validate(self.stored(report), 3, self.root), [])

    def test_rest_of_the_content_is_carried_over(self) -> None:
        before = kinds.read(self.path)
        stored = self.stored(self.call("--apply"))
        for key in ("uid", "protocol", "project", "interactions", "measurements"):
            self.assertEqual(stored[key], before[key])

    def test_without_apply_nothing_changes(self) -> None:
        report = self.call()
        self.assertEqual(report["result"], "PASS")
        self.assertTrue(self.path.exists())
        self.assertFalse((self.root / report["target"]).exists())


if __name__ == "__main__":
    unittest.main()
