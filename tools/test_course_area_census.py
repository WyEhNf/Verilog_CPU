"""Regression and negative controls for independent course hierarchy accounting."""
from copy import deepcopy
import unittest

from verify_course_axi_area import expand_stat_census


def row(leaves, modules=None):
    modules = modules or {}
    return dict(num_cells=sum(leaves.values()), num_submodules=sum(modules.values()),
                num_memories=0, num_memory_bits=0, num_processes=0,
                num_cells_by_type=leaves | modules)


def flat():
    top = row({'DFFHQNx1_ASAP7_75t_R': 7, 'fakeram_asap7_32x32': 3})
    return dict(modules={'\\student_top': deepcopy(top)}, design=deepcopy(top))


def nested():
    # The same functional module appears at two levels, with multiplicities
    # 3 directly and 2*4 through a wrapper. Every physical SRAM is counted.
    return dict(modules={
        '\\student_top': row({'INVx1_ASAP7_75t_R': 1}, {'bank': 3, 'wrapper': 2}),
        'bank': row({'DFFHQNx1_ASAP7_75t_R': 2, 'fakeram_asap7_32x32': 1}),
        'wrapper': row({'INVx1_ASAP7_75t_R': 1}, {'bank': 4}),
    }, design=row({'INVx1_ASAP7_75t_R': 3, 'DFFHQNx1_ASAP7_75t_R': 22,
                   'fakeram_asap7_32x32': 11}, {'bank': 11, 'wrapper': 2}))


class CensusTests(unittest.TestCase):
    def rejects(self, data):
        with self.assertRaises(AssertionError):
            expand_stat_census(data)

    def test_flat(self):
        leaves, hierarchy = expand_stat_census(flat())
        self.assertEqual(sum(leaves.values()), 10)
        self.assertFalse(hierarchy)

    def test_nested_real_multiplicity(self):
        leaves, hierarchy = expand_stat_census(nested())
        self.assertEqual(leaves['fakeram_asap7_32x32'], 11)
        self.assertEqual(sum(leaves.values()), 36)
        self.assertEqual(dict(hierarchy), {'bank': 11, 'wrapper': 2})

    def test_missing_top(self):
        data = nested()
        del data['modules']['\\student_top']
        self.rejects(data)

    def test_ambiguous_module_name(self):
        data = nested()
        data['modules']['\\bank'] = deepcopy(data['modules']['bank'])
        self.rejects(data)

    def test_recursive_hierarchy(self):
        data = nested()
        data['modules']['bank'] = row({}, {'wrapper': 1})
        self.rejects(data)

    def test_unreachable_module(self):
        data = nested()
        data['modules']['unpriced_stub'] = row({'unknown_leaf': 1})
        self.rejects(data)

    def test_module_leaf_total(self):
        data = nested()
        data['modules']['bank']['num_cells'] += 1
        self.rejects(data)

    def test_module_instance_total(self):
        data = nested()
        data['modules']['wrapper']['num_submodules'] -= 1
        self.rejects(data)

    def test_global_leaf_total(self):
        data = nested()
        data['design']['num_cells'] += 1
        self.rejects(data)

    def test_global_instance_total(self):
        data = nested()
        data['design']['num_submodules'] -= 1
        self.rejects(data)

    def test_global_unknown_extra_type(self):
        data = nested()
        data['design']['num_cells_by_type']['unpriced_stub'] = 1
        self.rejects(data)

    def test_global_leaf_swap_with_same_total(self):
        data = nested()
        data['design']['num_cells_by_type']['INVx1_ASAP7_75t_R'] += 1
        data['design']['num_cells_by_type']['DFFHQNx1_ASAP7_75t_R'] -= 1
        self.rejects(data)

    def test_sram_omission_even_with_adjusted_total(self):
        data = nested()
        del data['design']['num_cells_by_type']['fakeram_asap7_32x32']
        data['design']['num_cells'] -= 11
        self.rejects(data)

    def test_invalid_multiplicities(self):
        for value in (0, -1, 1.5, True):
            with self.subTest(value=value):
                data = nested()
                data['modules']['bank']['num_cells_by_type']['fakeram_asap7_32x32'] = value
                self.rejects(data)

    def test_unmapped_objects(self):
        for level in ('bank', 'design'):
            for field in ('num_memories', 'num_memory_bits', 'num_processes'):
                with self.subTest(level=level, field=field):
                    data = nested()
                    target = data['design'] if level == 'design' else data['modules'][level]
                    target[field] = 1
                    self.rejects(data)


if __name__ == '__main__':
    unittest.main(verbosity=2)
