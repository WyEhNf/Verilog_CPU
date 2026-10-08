# MSHR unowned write-data clear review

This is an unimplemented fallback area direction. The active combined PPA is frozen at a7e64b80 in F:/CPU2026TierRuns/tier1_shared_balanced_owner_20261009_r2; it must finish before deciding whether more area work is needed. No new RTL, simulation, synthesis, STA or perf is started for this review. All profiles retain the same parameterized CPU.

The actual bank at rtl/cache/rv32_dcache_mshr_data_bank.v retains 128 bits per MSHR. Its current highest-priority reset/prefetch event clears all bytes, a demand allocation/store promotion writes the whole line, and store merge writes only selected bytes. Each byte uses a two-event selector plus its original word owner. The clear event qualifies WDATA and all byte write enables even when no valid store can observe those bits.

The cache request action decoder in rv32_dcache_nonblocking.v distinguishes store promotion of a matching prefetch (action 6), store merge of a matching store (7), and new demand/around allocation (8/9). Promotion and allocation invoke the bank's whole-line write_word. The lifecycle sets mshr_store only on those two same-edge operations; reset/prefetch allocation set it to zero. Store merge preserves existing owned data and masks. A demand load allocation also writes the original full line; a load promotion of a prefetch changes its descriptor but leaves store false.

Every current architectural consumer of the bank's store-data word has store/mask authority:

- Matching-store forwarding requires matching_found, mshr_store and complete coverage of the requested mask. A valid store therefore started with a whole-line write before any merge. Keep the full originally supplied line, including unmasked bytes, to preserve the public word-response payload.
- Memory refill byte merge chooses store data only when response mshr_store is true and the corresponding saved mask bit is set. A nonstore/prefetch refill uses memory data.
- A local no-RFO fill candidate requires a valid store row, not sent/writeback/RFO-offered, with mask ffff.
- Normal memory writeback uses separately owned victim_data; writearound also uses victim_data captured from the allocation request. This proposal must not alter that victim owner. Read-command WDATA stays zero through its original write-valid mask.
- Reset invalidates all MSHR lifecycle owners. Prefetch allocation creates a valid nonstore owner with mask zero; its old store-data word should have no observable authority until a later whole-line store promotion initializes it.

A possible default-off MSHR_DATA_NO_CLEAR policy could suppress payload writes on reset/prefetch while retaining every existing lifecycle/mask clear, and use raw incoming WDATA on actual whole-line/masked-merge updates. It must continue to suppress simultaneous lower-priority writes whenever the old clear event is present. No register capacity, clock edge, byte merge priority, outstanding request identity or SRAM changes are permitted. The original bank remains mode zero. A simulation-only initialized certificate can assert that any valid store row has undergone a whole-line write since reset/prefetch reuse.

Before implementation, review the exact reset and prefetched-row collision ordering, the legacy/banked selection guard, prefetch-to-store promotion while an RFO is already offered, response failures, and all raw bank-data debug/public aliases. A finite paired cache sample would need deliberate nonzero stale bytes before reset/prefetch reuse, a valid nonstore refill, then store promotion and partial merging; compare public valid transfers/cycles and all enabled data. The previous narrow-query sample had PREFETCH=0, so it does not cover this ownership transition. No mapped area or timing saving is established by this review.

The expected opportunity is control and idle-data gating, not removing the 128 retained bits: multiword store coalescing can require all bytes. This may be too small by itself to justify another PPA and should be combined with further substantive changes only if the current measured result requires them.

Reviewed source SHA256:

- rtl/cache/rv32_dcache_nonblocking.v: 9d7c6cae3e7bec698a2ca0e2d32daa8c77de315869d146319f4129de009a9fde

- rtl/cache/rv32_dcache_mshr_data_bank.v: f9a71ce8d8d147b9c115b277718da9b378029861f7ff598669bbe1ce13621b73
