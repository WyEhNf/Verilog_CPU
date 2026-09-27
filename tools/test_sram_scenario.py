import unittest
from estimate_local_sram_floor import physical_memories


class PhysicalGeometryTests(unittest.TestCase):
    def fixture(self):
        params = {key: format(value, '032b') for key, value in
                  dict(WIDTH=32, SIZE=64, RD_PORTS=1, WR_PORTS=1).items()}
        return dict(memory_boundaries=2, memories=[
            dict(instance='predictor0.target', parameters=params),
            dict(instance='predictor1.target', parameters=params)])

    def test_repeated_geometry_counts_every_instance(self):
        rows = physical_memories(self.fixture())
        self.assertEqual(len(rows), 2)
        self.assertEqual(sum(row['bits'] for row in rows), 4096)

    def test_reject_unknown_shape_and_mismatched_inventory(self):
        manifest = self.fixture()
        manifest['memory_boundaries'] = 3
        with self.assertRaises(ValueError):
            physical_memories(manifest)
        manifest = self.fixture()
        manifest['memories'][0]['parameters']['WIDTH'] = 'xxxx'
        with self.assertRaises(ValueError):
            physical_memories(manifest)


if __name__ == '__main__':
    unittest.main()
