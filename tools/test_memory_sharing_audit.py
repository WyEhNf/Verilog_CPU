import copy
import unittest

from audit_synth import AuditError, validate_cache_memory_sharing


class CacheSharingAuditTests(unittest.TestCase):
    def fixture(self):
        return [dict(module='param\\rv32_dcache_nonblocking', cell='data_mem',
                     width=128, size=1024, abits=10, rd_ports=1, wr_ports=4),
                dict(module='param\\rv32_lsq', cell='data_mem',
                     width=32, size=8, abits=3, rd_ports=9, wr_ports=132)]

    def test_cache_consolidation(self):
        before = self.fixture()
        after = copy.deepcopy(before)
        after[0]['wr_ports'] = 2
        self.assertEqual(validate_cache_memory_sharing(before, after)[0]['after'], [1, 2])

    def test_reject_scope_geometry_and_identity_changes(self):
        before = self.fixture()
        for index, field, value in ((1, 'wr_ports', 12), (0, 'width', 64),
                                    (0, 'cell', 'other'), (0, 'wr_ports', 0),
                                    (0, 'rd_ports', 2)):
            after = copy.deepcopy(before)
            after[index][field] = value
            with self.subTest(field=field, index=index):
                with self.assertRaises(AuditError):
                    validate_cache_memory_sharing(before, after)


if __name__ == '__main__':
    unittest.main()
