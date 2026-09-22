"""Demand-only cache shadow experiment, NOT an RTL IPC/cache-miss measurement.

Replay accepted dreq addresses from cpu_core_image_tb +TRACE. Sequential fills,
no prefetch, no MSHRs or memory timing; useful only to select RTL experiments.
"""
import argparse
from collections import OrderedDict
import json
from pathlib import Path
import re


class ShadowCache:
    def __init__(self, lines, ways=1, hashed=False):
        if lines < 1 or ways < 1 or lines % ways:
            raise ValueError("lines must be a positive multiple of ways")
        self.sets = lines // ways
        if self.sets & (self.sets - 1):
            raise ValueError("set count must be a power of two")
        self.ways, self.hashed = ways, hashed
        self.shift = self.sets.bit_length() - 1
        self.entries = [OrderedDict() for _ in range(self.sets)]
        self.requests = self.misses = self.dirty_evictions = 0

    def access(self, address, store):
        line = address >> 4
        index = line ^ (line >> self.shift) if self.hashed else line
        bucket = self.entries[index & (self.sets - 1)]
        self.requests += 1
        hit = line in bucket
        if not hit:
            self.misses += 1
            if len(bucket) == self.ways:
                _, dirty = bucket.popitem(last=False)
                self.dirty_evictions += bool(dirty)
            bucket[line] = False
        bucket[line] |= store
        bucket.move_to_end(line)
        return hit

    def summary(self):
        return dict(requests=self.requests, misses=self.misses,
                    miss_rate=self.misses / self.requests if self.requests else 0,
                    dirty_evictions=self.dirty_evictions)


def analyze(path):
    caches = {}
    for lines in (64, 128, 256):
        for label, ways, hashed in (("direct", 1, False), ("xor-direct", 1, True),
                                    ("2way-lru", 2, False), ("4way-lru", 4, False),
                                    ("fully-associative-lru", lines, False)):
            caches[f"{lines * 16}B/{label}"] = ShadowCache(lines, ways, hashed)
    pattern = re.compile(r"dreq load=([01]) store=([01]) addr=([0-9a-fA-F]{8}) .*ready=1$")
    passed = False
    with path.open(encoding="utf-8-sig") as stream:
        for text in stream:
            if "FAIL:" in text:
                raise ValueError("Trace contains an RTL failure")
            passed |= "PASS: JOIN-02" in text
            match = pattern.search(text.strip())
            if match:
                load, store, address = match.groups()
                if load == store:
                    raise ValueError("Accepted request is not exclusively a load or store")
                for cache in caches.values():
                    cache.access(int(address, 16), store == "1")
    if not passed or not next(iter(caches.values())).requests:
        raise ValueError("Expected a passing RTL trace with accepted requests")
    return {"trace": str(path), "model": "serial demand-only shadow; not RTL performance",
            "caveats": ["No prefetch, MSHR merging, memory latency or speculative refill effects",
                        "Request order taken from baseline RTL; another design may reorder requests",
                        "Dirty evictions exclude a final cache drain; no area or frequency estimate"],
            "caches": {name: cache.summary() for name, cache in caches.items()}}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = analyze(args.trace)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
