# Static sentinel class and saved candidate-state query

## Measured reason and candidate boundary

The db75467c MMIO STORE-admission routing candidate failed both gates: 9032.621455 um² / 244.858919 MHz. It is rejected; no CPU build/perf/smoke was run. Its longest path is Icache → backend architectural source RS1 → RAT/PRF → fresh LSQ offer → candidate-state query → forwarding admission → saved selection payload write. RS1[4] reaches 2.100 ns, with a NAND2 delay of 0.548 ns and following inverter delay of 0.414 ns. Source field alias was checked in mapped.v. This is real mapped timing evidence, not a predicted gain.

The new profile `configs/tier1_shared_static_source_query.json` derives from the better measured `8af905db` fresh-data profile (8973.514135 um² / 294.930876 MHz). It explicitly disables the failed MMIO_STORE_ADMISSION_ROUTE policy, while retaining the existing saved-class routing. It adds two default-off policies of the same shared CPU/backend/LSQ; no width-specific CPU or new pipeline edge is introduced. No new area, frequency or IPC is claimed yet.

## DECODE_STATIC_HALT_CLASS

When enabled, is_halt_trace is parameter-qualified by LEGACY_SENTINEL_HALT. If that legacy parameter is nonzero, every bit and original HALT behavior remains the original opcode comparison. If it is zero, the source/opcode HALT selectors become constant false. Shared decoder RTL assigns HALT only under the legacy parameter and exact sentinel word override; all other valid or illegal instruction words cannot produce HALT. A decoded queue writes those decoder packets, and occupied-row/input-bypass validity preserves this invariant. Invalid stale queue data can differ in source/opcode selection, but cannot create a dispatch because trace validity is still required. The original queue valid, acceptance and invalidation logic is unchanged.

Core simulation asserts that every valid downstream decoded packet is non-HALT whenever this policy is enabled and the sentinel parameter is zero. The existing legacy-enabled sentinel behavior is retained, and the sentinel word is ordinary ADDI in the disabled mode. There is no whitelist of benchmark instructions or opcode/tag width narrowing. Detailed invariant review: `docs/disabled_halt_source_query_review_2026-10-09.md`. No additional decoder/whole-CPU correctness sweep is justified for this static invariant; structural lint and later gated CPU perf/smoke will use the production assertion.

## LSQ_SAVED_CANDIDATE_STATE_QUERY

When enabled, the existing 4-bit candidate state reader indexes the slot of existing_selection_packet directly, instead of candidate_found ? visible selected_slot : 0. It requires LSQ_SAVED_REQUEST_QUERY. The packet remains the original held/direct old selection, with its original complete ownership/tag/GEN checks. It changes no stored bits.

If candidate_found is true, fresh allocation request offer is false: a fresh offer requires !selection_valid and !pick_valid, whereas candidate_found in pipelined LSQ is selection_live OR selection_direct_bypass. Thus the visible selection equals the old packet, and the new and old queried slot/state are identical. Nonpipelined LSQ cannot offer a fresh request and has the same property. If candidate_found is false, metadata_forward and qualified MMIO STORE-valid are already false. Generic admission is false unless a fresh request is offered; that alternative already overrides wait_i to zero. Therefore arbitrary old-row query data is unowned and cannot affect actual admission, forwarding, metadata writes or handshakes. All uses of candidate_wait/load/sent/complete were inspected.

Simulation reads the original query in parallel and compares all four fields on every non-reset edge with candidate_found. The original full selection generation/live checks, full tags and forwarding data/masks remain intact. This removes the unnecessary fresh-offer/visible packet and candidate_found qualification from the state-query index path, without speculative acceptance or weakened identity checks.

One finite paired BE2/LSQ4 sample with policy 0/1 passed fresh/held requests, partial/full forwarding, delayed store data, held result, full-row load-pop/store-reuse and stale response, MMIO held/stale/fresh-load class and recovery guard. It compares valid public request and completion packets, handshakes and cycle/occupancy plus original query assertions. Both DUTs use saved query/phased owner and the same generic valid-qualified route. RELEASE_CREDITS=2 is only the reuse fixture; production Tier1 is 0. It does not instantiate cpu_core and does not claim to test the static HALT CPU policy. Evidence: `reports/Tier_shared_LSQ_saved_state_protocol_2026-10-09.json`.

## Evaluation

Freeze once, original structural lint once, full official PPA once. Only after both area <=9000 and frequency >=300, build once and run the six official perf cases. Require IPC >=0.6000 and no cycle regression versus c2a09eaa (12249/23982/231173/455096/7515/9007). Only after all gates pass run correctness_array_test1 once. Historical accepted Tier2/Tier3 remain their exact freezes; defaults are unchanged and no canonical profile is replaced by an unaccepted candidate.

## Terminal result

One full official PPA on e776571f measured 9069.333895 um2 / 290.49645390070924 MHz. Both gates fail; area +95.819760 um2 and frequency -4.434422 MHz versus 8af905db. No CPU build/perf/smoke was run, IPC is unmeasured, and no accepted profile was replaced. The new worst path returns to D-cache metadata, LSQ response/completion, ROB live query, LSQ selection/forward admission, qualified MMIO exit distribution and bus read lifecycle. Minimum period is 3.4423828125 ns and worst arrival is 3.3826 ns. This failed combined policy is not accepted as a new tier.
