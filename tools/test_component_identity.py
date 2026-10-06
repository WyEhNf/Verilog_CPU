"""Small parser/fingerprint checks; not hardware or CPU equivalence."""
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from audit_component_timing_identity import declarations, fingerprint


class IdentityChecks(unittest.TestCase):
    def test_module_header_without_space(self):
        source = 'module student_top(clk_i, data);\n  INVx1 gate (\nendmodule\n'
        with patch.object(Path, 'read_text', return_value=source):
            self.assertEqual(declarations(Path('unused.v')), [('student_top', 'INVx1', 'gate')])

    def test_escaped_parameterized_namespace(self):
        source = 'module \\$paramod$123\\bank (clk_i);\n  DFF \\$hidden$9 (\nendmodule\n'
        with patch.object(Path, 'read_text', return_value=source):
            self.assertEqual(declarations(Path('unused.v')),
                             [('$paramod$123\\bank', 'DFF', '$hidden$9')])

    @staticmethod
    def graph(offset=0, escaped=False, changed_child=False):
        def module(child):
            return dict(netnames={'a': {'bits': [2+offset]},
                                  'y': {'bits': [3+offset]}},
                        ports={'a': {'direction': 'input', 'bits': [2+offset]},
                               'y': {'direction': 'output', 'bits': [3+offset]}},
                        cells={'cell': {'type': child, 'parameters': {},
                                        'connections': {'A': [3+offset if changed_child and child == 'INV' else 2+offset],
                                                        'Y': [3+offset]}}})
        return {'modules': {'student_top': module('bank'),
                            ('\\bank' if escaped else 'bank'): module('INV')}}

    def value(self, **settings):
        with patch.object(Path, 'read_text', return_value=json.dumps(self.graph(**settings))):
            return fingerprint(Path('unused.json'), {'student_top', 'bank'})

    def test_fingerprint_uses_aliases_not_json_bit_ids(self):
        self.assertEqual(self.value(), self.value(offset=50))

    def test_fingerprint_checks_child_pin(self):
        self.assertNotEqual(self.value(), self.value(changed_child=True))

    def test_fingerprint_normalizes_only_unambiguous_module_escape(self):
        self.assertEqual(self.value(), self.value(escaped=True))
        graph = self.graph()
        graph['modules']['\\bank'] = graph['modules']['bank']
        with patch.object(Path, 'read_text', return_value=json.dumps(graph)):
            with self.assertRaisesRegex(AssertionError, 'Ambiguous'):
                fingerprint(Path('unused.json'), {'student_top', 'bank'})


if __name__ == '__main__':
    unittest.main()
