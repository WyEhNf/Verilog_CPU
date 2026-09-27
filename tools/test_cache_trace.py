import unittest
from analyze_cache_trace import ShadowCache


class CacheTests(unittest.TestCase):
    def test_xor_breaks_power_of_two_conflict(self):
        direct, hashed, two_way = ShadowCache(64), ShadowCache(64, hashed=True), ShadowCache(64, 2)
        for line in (0, 64, 0, 64):
            for cache in (direct, hashed, two_way):
                cache.access(line * 16, False)
        self.assertEqual((direct.misses, hashed.misses, two_way.misses), (4, 2, 2))

    def test_lru_and_dirty_eviction(self):
        cache = ShadowCache(2, 2)
        for line, store in ((0, True), (1, False), (0, False), (2, False), (3, False)):
            cache.access(line * 16, store)
        self.assertEqual(cache.misses, 4)
        self.assertEqual(cache.dirty_evictions, 1)
        self.assertEqual(list(cache.entries[0]), [2, 3])

    def test_reject_bad_capacity(self):
        for lines, ways in ((0, 1), (4, 0), (4, 3), (6, 1)):
            with self.assertRaises(ValueError):
                ShadowCache(lines, ways)


if __name__ == "__main__":
    unittest.main()
