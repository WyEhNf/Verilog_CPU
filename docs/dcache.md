# A-05 D-Cache

`rv32_dcache` is a 4 KiB direct-mapped cache with 16-byte lines and
write-back/write-allocate replacement. Each request carries the LSQ and ROB
tags; loads return the complete line plus an extracted byte/half/word value,
while committed stores merge their 16-bit byte mask into the line and return a
store acknowledge.

Hits pass through three registered stages. A miss uses one MSHR. A dirty victim
is written back as a full line before the requested line is refilled from the
H-03 memory port. Refill data is installed even when a load response is later
dropped by `flush_i`; stores are never canceled once accepted by the cache.
Memory address/ID mismatches remain unconsumed, and memory errors become
deterministic tagged load errors or store-ack errors.

Verification entry `make a05` uses the real 50-cycle dual-port memory model and
covers cold and warm accesses, measured three-stage hit timing, stable response
payloads under backpressure, byte merge and signed extraction, dirty conflict
eviction/writeback, flushed load misses, and out-of-range memory errors.
