# Completion source-side ROB state query

## Measured reason

The aea34a6f Tier1 freeze measured 8893.003375 um2 / 290.578888 MHz and was rejected without CPU build/perf/smoke. Its longest response-to-request path goes through the direct completion selected tag, then the three-bit ROB state reader, before ROB completion/commit qualification and the next LSQ request. The post-arbitration state reader ends around 1.8925 ns in that report; the complete path arrives at the phased LOAD result owner at 3.3968 ns. This is an actual mapped path observation, not a new timing estimate for the change below.

## Same lookup, different order

COMPLETION_SOURCE_STATE_QUERY defaults to zero in the shared course top/core/backend. Mode one requires COMPLETION_BYPASS=2. No alternative CPU/backend is introduced, no pipeline stage or storage bit is added, and source priority, held-result ownership, CDB readiness, recovery shifting and all original valid/full-tag/generation checks remain unchanged.

The direct completion network exports the exact selected source mask already used to select its tag/value payload, including its original reset/flush qualification. Non-direct modes export zero. The backend reads the current {load_error_mem, rob_mem_size_mem} table using each source identity before arbitration, then chooses those three bits with the original source mask. It does not cache metadata: a stalled source sees the same current table contents that the old selected-tag reader would see on each edge. It does not assume that an unreported LOAD has a zero error flag or omit any identity check.

For ALU/MDU, the registered source tag drives the same array lookup. A LOAD with the existing early head/saved/held identity query reads each original candidate with that exact candidate query, then uses the unchanged head/saved/held choice. A LOAD without those early identities uses its existing predecoded report query, or its original raw report tag when predecode is disabled. The current table, complete tags, explicit range tests, live generation predicates, same-edge LOAD-error contribution and STORE size-to-mask conversion remain intact.

For one valid selected source j, its selected CDB tag equals source j's tag; selecting table[source[j]] therefore equals table[selected_tag]. The network has at most one source per direct CDB lane. Invalid metadata values may differ, but all consuming normal and shifted recovery packets retain their original validity gates. In simulation every valid ROB writeback, including a stalled CDB lane, checks both one-hot source ownership and equality of all three bits against the original selected-tag lookup. The reference reader is simulation-only; mode zero retains the original reader.

## Evaluation boundary

Use one finite paired actual BE2/ROB8/PHYS40/RS4/LSQ4 backend stimulus with source state 0/1, direct and staged recovery, head/saved LOAD identity and held identity enabled in one pair. It reuses the pending-recovery sequence, then samples SB/SH/SW requests with real ACKs and a head LOAD error (no response-edge commit, then the original registered terminal record). Public valid packets/cycles, ROB/allocator state, exact STORE masks/words and the original selected-state assertions are compared. This is a bounded protocol sample, not a whole CPU or backend proof.

The Tier1 profile derives from the latest direct phased-event candidate and enables only this new policy. After the finite sample, run one committed freeze, one original structural full-core lint and one official PPA. Require area <=9000 and frequency >=300 before CPU build/perf. Require IPC >=0.6000 and no per-case cycle regression from c2a09eaa before one array1 smoke. No CPU metrics or accepted-profile replacement are established by the implementation or parameter checker.

## Finite stimulus correction

The first run and its diagnostic rerun reached the final error LOAD without any source-state equality assertion failure. The fixture incorrectly forbade the original registered error terminal commit record. The diagnostic showed both reference/new pairs have response valid/error with no commit at 775 ns, then registered head-ready/head-error and the terminal record at 785 ns. Original ROB logic deliberately publishes that terminal record before setting error_o and blocks younger lanes. The fixture was corrected to expect the record and separately assert no response-edge commit plus registered error state; no production RTL fix was needed. Both failed fixture logs are retained, and the corrected sample remains the same bounded sequence.

## Bounded sample result

The corrected sequence passed once. Exact frozen source/executable/build/simulation hashes, elapsed time and both retained fixture failures are in reports/Tier_shared_completion_source_state_protocol_2026-10-09.json. Each actual reference/new backend pair retained identical valid public packets, handshake cycles and ROB/allocator state. SB/SH/SW masks and words, real ACKs, response-edge error suppression and the original registered terminal record were checked. The production original-state equality assertion remained active on every valid ROB writeback. This sample is not CPU IPC/PPA evidence.
