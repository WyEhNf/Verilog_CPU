import unittest
from inventory_unpriced_storage import inventory


class StorageInventoryTests(unittest.TestCase):
    def fixture(self):
        params = {k: format(v, '032b') for k, v in
                  dict(WIDTH=32, SIZE=16, RD_PORTS=2, WR_PORTS=1).items()}
        manifest = dict(memory_boundaries=2, memories=[
            dict(instance=n, parameters=dict(params)) for n in ('a', 'b')])
        logic = dict(unpriced_leaves=2, combinational_standard_cell_area_um2=1.1,
                     sequential_standard_cell_area_um2=2.2,
                     known_timed_standard_cell_area_um2=3.3)
        return manifest, logic

    def test_counts_instances_not_definitions_and_never_zero_prices(self):
        result = inventory(*self.fixture())
        self.assertEqual(result['logical_storage_bits'], 1024)
        self.assertIsNone(result['total_area_um2'])
        self.assertIsNone(result['sram_area_um2'])
        self.assertEqual(result['port_histogram'][0]['instances'], 2)

    def test_separates_rom_without_assuming_sram(self):
        manifest, logic = self.fixture()
        manifest['memories'][0]['parameters']['WR_PORTS'] = '0' * 32
        result = inventory(manifest, logic)
        self.assertEqual(result['read_only_bits'], 512)
        self.assertEqual(result['read_only_instances'], 1)

    def test_rejects_mismatches_and_duplicate_instances(self):
        manifest, logic = self.fixture()
        logic['unpriced_leaves'] = 1
        with self.assertRaises(ValueError):
            inventory(manifest, logic)
        manifest, logic = self.fixture()
        manifest['memories'][1]['instance'] = 'a'
        with self.assertRaises(ValueError):
            inventory(manifest, logic)


if __name__ == '__main__':
    unittest.main()
