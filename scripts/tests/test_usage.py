#!/usr/bin/env python3
"""Tests of the shape the scripts of this repository answer --usage with."""

import contextlib
import io
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import usage


class AskedTest(unittest.TestCase):

    def test_flag_after_the_name_asks(self):
        self.assertTrue(usage.asked(["skrypt.py", "--usage"]))
        self.assertTrue(usage.asked(["skrypt.py", "plik.json", "--usage"]))

    def test_no_flag_does_not_ask(self):
        self.assertFalse(usage.asked(["skrypt.py", "plik.json"]))

    def test_the_name_of_the_script_is_not_the_flag(self):
        self.assertFalse(usage.asked(["--usage"]))


class ShapeTest(unittest.TestCase):

    def test_command_carries_the_required_keys(self):
        entry = usage.command("run", "Sprawdza pomiary.")
        self.assertEqual(sorted(entry), ["changes", "name", "summary"])

    def test_empty_lists_are_left_out(self):
        self.assertNotIn("arguments", usage.command("run", "Opis.", arguments=[]))

    def test_plain_names_one_command(self):
        commands = usage.plain("Sprawdza pomiary.")
        self.assertEqual(len(commands), 1)
        self.assertEqual(commands[0]["name"], usage.PLAIN_COMMAND)

    def test_report_has_the_required_keys(self):
        answer = usage.report("validate.py", usage.plain("Sprawdza."))
        self.assertEqual(answer["result"], "PASS")
        self.assertEqual(answer["name"], "validate.py")
        self.assertTrue(answer["commands"])

    def test_emit_prints_json_and_returns_zero(self):
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            code = usage.emit(usage.report("validate.py", usage.plain("Sprawdza.")))
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(stream.getvalue())["name"], "validate.py")


if __name__ == "__main__":
    unittest.main()
