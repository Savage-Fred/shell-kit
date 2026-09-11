#!/usr/bin/env python3
"""Synthetic-only safety and lexical tests for the names-only inventory."""
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from audit_secrets import audit_file, inspect_text, main

CANARY = 'C4NARY_private_value_NEVER_OUTPUT'


class AuditTests(unittest.TestCase):
    def assert_names(self, source, expected, warnings=None):
        result = inspect_text(source)
        self.assertEqual([item['name'] for item in result['names']], expected)
        if warnings is not None:
            self.assertEqual(result['parse_warning_count'], warnings)
        self.assertNotIn(CANARY, json.dumps(result))
        return result

    def test_basic_export_whitespace_and_equals(self):
        self.assert_names('export A=' + CANARY + '\n B = "a=b=c"\nEMPTY=\n',
                          ['A', 'B', 'EMPTY'], 0)

    def test_comments(self):
        self.assert_names('# ' + CANARY + '\nA=x # ' + CANARY + '\nB="x#y"\nC=x#y\n',
                          ['A', 'B', 'C'], 0)

    def test_multiline_single_quote(self):
        result = self.assert_names("A='" + CANARY + "\nFAKE=private\n'\nB=ok\n", ['A', 'B'], 0)
        self.assertEqual([entry['line'] for entry in result['names']], [1, 4])

    def test_multiline_double_quote(self):
        self.assert_names('A="' + CANARY + '\nFAKE=private\n"\nB=ok', ['A', 'B'], 0)

    def test_unclosed_quote_suppresses_remainder(self):
        self.assert_names("A=ok\nB='" + CANARY + '\nFAKE=value\n', ['A'], 1)

    def test_command_substitution_never_executes(self):
        self.assert_names('A=$(printf ' + CANARY + '\nFAKE=value\n)\nB=ok', ['A', 'B'], 0)

    def test_nested_substitution_and_quotes(self):
        self.assert_names('A="$(printf \'"\'; echo "$(echo x)")"\nB=ok', ['A', 'B'], 0)

    def test_backticks(self):
        self.assert_names('A=`echo ' + CANARY + '\nFAKE=value\n`\nB=ok', ['A', 'B'], 0)

    def test_parameter_substitution(self):
        self.assert_names('A="${OTHER:-${MORE:-' + CANARY + '}}"\nB=ok', ['A', 'B'], 0)

    def test_semicolon_assignments(self):
        result = self.assert_names('A=x; export B="x;y"; A=z\n', ['A', 'B', 'A'], 0)
        self.assertEqual(result['duplicates'], [{'name': 'A', 'lines': [1, 1], 'count': 2}])

    def test_space_assignments_ambiguous(self):
        self.assert_names('A=x B=' + CANARY + '\nC=y', ['C'], 1)

    def test_unknown_commands_and_malformed_lines(self):
        self.assert_names('echo ' + CANARY + '\n9KEY=x\nA x\nB=ok', ['B'], 3)

    def test_escaped_newline(self):
        self.assert_names('A=' + CANARY + '\\\nFAKE=value\nB=ok', ['A', 'B'], 0)

    def test_escaped_quotes(self):
        self.assert_names('A="a\\"b"\nB=\'c\'\n', ['A', 'B'], 0)

    def test_arrays_suppress_embedded_names(self):
        self.assert_names('A=(one\nFAKE=value\ntwo)\nB=ok', ['A', 'B'], 0)

    def test_heredoc_abandons_remainder(self):
        self.assert_names('A=x\ncat <<EOF\nFAKE=' + CANARY + '\nEOF\nB=ok', ['A'], 1)

    def test_unclosed_substitution(self):
        self.assert_names('A=$(echo x\nFAKE=' + CANARY + '\nB=ok', [], 1)

    def test_operators_are_ambiguous(self):
        self.assert_names('A=x&&echo ' + CANARY + '\nB=x|cat\nC=x>output\nD=ok', ['D'], 3)

    def test_no_values_in_cli_or_errors(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / CANARY
            path.write_text('# ' + CANARY + '\nexport API_TOKEN="' + CANARY + '"\n')
            path.chmod(0o600)
            for option in ([], ['--json']):
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    self.assertEqual(main(option + [str(path)]), 0)
                self.assertNotIn(CANARY, output.getvalue())
                self.assertIn('API_TOKEN', output.getvalue())
                self.assertIn('0600', output.getvalue())
            self.assertEqual(audit_file(str(path) + 'missing'), {'error': 'unreadable_file'})

    def test_invalid_utf8_no_exception_text(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / CANARY
            path.write_bytes(b'API_TOKEN=\xff')
            self.assertEqual(audit_file(path), {'error': 'unreadable_file'})

    def test_command_substitution_has_no_side_effect(self):
        with tempfile.TemporaryDirectory() as folder:
            marker = Path(folder) / 'never-created'
            path = Path(folder) / 'synthetic.env'
            path.write_text('TOKEN=$(touch ' + str(marker) + ')\n')
            result = audit_file(path)
            self.assertEqual(result['names'], [{'name': 'TOKEN', 'line': 1}])
            self.assertFalse(marker.exists())

    def test_fifo_is_rejected_without_reading(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'fifo'
            os.mkfifo(path)
            self.assertEqual(audit_file(path), {'error': 'not_regular_file'})

    def test_help_aliases_and_no_default_file(self):
        script = Path(__file__).with_name('audit_secrets.py')
        for arg in ('-h', '--help', 'help'):
            result = subprocess.run([sys.executable, str(script), arg], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0)
            self.assertIn('never sourced or evaluated', result.stdout)
        result = subprocess.run([sys.executable, str(script)], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)


if __name__ == '__main__':
    unittest.main()
