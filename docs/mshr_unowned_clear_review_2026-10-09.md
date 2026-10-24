# MSHR unowned write-data clear review

The following is the historical preimplementation area review at a7e64b80. At that point no RTL or evaluation of this direction was started. A later implementation is documented below. All profiles retain the same parameterized CPU.

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

## Later implementation: DCACHE_MSHR_DATA_NO_CLEAR

The core/top policy defaults to zero and passes MSHR_DATA_NO_CLEAR to the same nonblocking cache and NO_UNOWNED_CLEAR to its existing data banks. It requires banked STATIC_UPDATES=2 and a nonblocking cache. Mode zero preserves the original clear selector. Mode one retains all 128 bits and byte owners but drives raw incoming byte data and writes only when update AND NOT (reset OR this-row-prefetch-clear). Reset and prefetch therefore still win over simultaneous allocation/merge; their existing lifecycle and mask writes are unchanged. No SRAM, queue capacity, tag/generation or clock edge changes.

Cache lifecycle ordering was checked directly: reset clears valid/store; prefetch allocation is the last allocation writer and clears store; new demand/around allocation and store promotion establish store on the same edge as a complete data-bank word write. Merge retains the original owned word and writes only enabled bytes. Response failure clears lifecycle authority without publishing unowned bank bytes; victim data and writearound data remain in their separate original owner. No-clear changes neither response/error classification nor those byte consumers.

A simulation-only initialized certificate clears on reset/prefetch reuse, sets on a complete word write, and asserts before a masked merge. The actual cache additionally asserts that every valid store row has that initialized certificate. This state is excluded from synthesis. Full masks and complete original data remain important even for word responses: masked refill, forwarding and a later full-line dirty writeback must agree exactly.

The finite paired cache fixture uses PREFETCH=1, word responses, held RFO/ACK/response and no-clear 0/1. It deliberately seeds both banks with nonzero data, resets them, promotes a stale prefetch into a store, merges a second partial store, checks words and all 128 bytes of the actual dirty writeback, then reuses stale bytes as a nonstore prefetch and checks its memory result. It compares every valid public transfer and handshake cycle. Initial fixture failures were not equivalence failures: both implementations held a second miss to the same set while the first refill was stalled, then the fixture incorrectly expected full line-data from a WORD_RESPONSE interface. Those assumptions were corrected; frozen failed logs are retained. A finite sample is not a whole-cache or whole-CPU proof.
