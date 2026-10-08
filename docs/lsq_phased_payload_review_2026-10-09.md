# Review of phased LSQ payload storage, 2026-10-09

This is a source review of `5f4e376e`, not an implemented policy or a measured
optimization. The shared PRF-port/saved-query PPA is running separately.

The existing LSQ retains three independent 32-bit payloads per row:
`data_mem` for a store operand, `forward_data_mem` for an outstanding load's
partial forwarding, and `complete_value_mem` for a completed load. Their
ownership appears separable by instruction class and load phase:

| Live row phase | Word that can be consumed |
|---|---|
| Store, including uncommitted/committed/held request | store operand |
| Load before cache-request acceptance | no retained result/forward word |
| Load waiting for its cache response | saved partial-forward word |
| Load completed, including a stalled or held report | complete result |

Source consumers are request packets/forward windows (`data_mem`), the
full-generation-qualified response query (`forward_data_mem`), and the
load-only report packet (`complete_value_mem`). Metadata, complete error,
full ROB/LSQ tags, forwarding mask and request ownership must stay unchanged.
The cache response combines the OLD partial word with returned bytes before
capturing the resulting NEW word. Full forwarding completes directly without
accepting a cache request. Completing a load clears response wait, so a
subsequent duplicate response cannot legitimately consume its old forward word.

A possible default-off shared-word policy must preserve these priorities:

1. Any actual allocation of this physical row wins over old response/forward/
   data-update events. Choose the highest allocation lane, as the existing
   selectors do. A store gets its actual allocated operand; a load gets zero.
   Assert each actual allocation has exactly one of load/store set.
2. With no allocation, an existing store accepts only its original data-update
   selector. Cache ACK/result events must not overwrite its operand. Store
   forwarding and retained request payload remain byte-exact.
3. With no allocation, an existing load accepts result events (response or full
   forwarding) before request-forward events. Ignore irrelevant store-data
   updates/wakeups. After completion, retain the result through report stalls.
4. For a row reused on the response/report/pop edge, existing consumers read
   the old word combinationally and the new allocation owns the next edge.
   Recovery retains original response-cancel qualification and disallows fresh
   allocation. Invalid payload values have no authority.

A single short paired BE2/LSQ4 sample should cover partial forwarding followed
by cached byte merge, full-forward completion, delayed store data, held load
report, same-edge pop/reallocation and stale full-generation responses. No
whole correctness suite or capacity/policy sweep is justified.

If safe and useful, three banks becoming one remove 64 FF bits per LSQ row
(256 bits for LSQ4). This is a structural count only; selector changes and
mapping may offset savings. No area, frequency or IPC improvement is claimed.
It remains part of the same parameterized LSQ at every width.
