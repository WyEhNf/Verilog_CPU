# No-release phased LSQ capture

## Measured motivation

Tier1 509377c4 remains accepted at 8968.688155 um2 / 305.854241 MHz / IPC 0.6012842155901663. The current-source Tier2 c85c56ea freeze measured 17336.078412 um2 / 343.854936 MHz. Its area improves 660.940560 um2 from historical 5be74e01, but frequency regresses 11.824119 MHz. No build/perf/smoke ran; IPC is unknown. The worst arrival is 2.848 ns / period 2.908203125 ns.

The measured path goes from memory-bridge error/D-cache response through LOAD report/CDB/PRF credit into d_valid[0], then LSQ allocation and the lower-priority partial-forward grant before phased-word capture. A late allocation predicate suppresses an existing valid-row data event, despite allocation and a currently valid row being mutually exclusive under the production no-release policy. This follow-up changes that actual control path. The historical Tier3 ALU/arbitration path was reviewed only; no arithmetic precomputation is implemented or claimed.

## One shared default-off policy

LSQ_PHASED_ALLOC_EXCLUSIVE is a default-zero boolean passed through the same course top, cpu_core, rv32_backend_joint and LSQ. It requires phased data, direct write events, DIRECT_DISPATCH_RELEASE_CREDITS=0 and LSQ_DIRECT_POP_CREDIT=0. The generic LSQ additionally rejects any RELEASE_CREDITS!=0. No width-specific CPU, queue capacity, pipeline stage, extra storage word, full-tag width, clock edge or handshake is introduced. Accepted canonical profiles are left unchanged.

The original direct event order is STORE updates/wakes, partial-forward capture, fully forwarded result, response result, allocation lanes. With this policy, the original last-event priority is retained within the live-row group and within allocation lanes. Their already-qualified 32-bit words are OR-composed; write enable remains the OR of the same original events. The allocation predicate no longer masks every live-row grant.

## Ownership argument

With RELEASE_CREDITS=0, free_count is LSQ_ENTRIES minus pre-edge occupancy. Current-cycle pops contribute no capacity. Actual allocation slots come from the pre-edge tail and the accepted sparse memory prefix, so all allocations stay in the currently free interval. Metadata normally invalidates only the popped head prefix; selective recovery truncates the speculative suffix and updates tail/occupancy on the recovery edge, when normal allocations are disabled. Reset/whole flush clear lifecycle authority and likewise disable payload allocations. Committed stores and unreported loads retain their original FIFO membership. None of these lifecycle or identity rules is changed.

The existing ALLOC_SLOT_PRESELECT caller contract still requires its plan to equal actual fire whenever any allocation occurs. Production assertions now compare each actual payload allocation slot to its original full emitted LSQ tag slot, reject allocation of a currently valid row, and reject simultaneous live-group/allocation-group writes for a row. All full generation, response, forwarding, recovery, report and architectural admission checks remain in place. This certificate does not support borrowing a row released on this edge; the parameter guards explicitly reject that configuration.

An exact original four-phase selector remains simulation-only and compares every write enable and every complete selected word, including allocation/response priority. The new policy does not assume STORE update lanes are one-hot or change their last-lane ordering.

## Qualified data owner

Every event selector outputs zero when it has no event. Therefore the OR-composed data is zero whenever its OR-composed write is zero. For such input, D=data | (Q & !write) equals the former write ? data : Q. The generic qualified word bank retains the same unreset FF count, same pre-edge old consumers, allocation zeroing and full-word write edges, while omitting a redundant qualification of already-selected input data. It distributes hold control to at most 16 existing bits per leaf, using the existing bounded control tree. Its idle-zero input contract is checked each simulation edge. This OR/hold implementation is directly simulated even under WORD_SIM; it is not hidden behind the original if-write simulator branch.

The policy uses this bank only for the existing phased LSQ word. Other LSQ fields and every other word bank keep their original implementation. No arbitrary raw/PRF data is admitted to a qualified bank. No false path, timing exception, SRAM change or area exemption is added.

## Finite sample and evaluation

One BE2/LSQ4 old/new pair passed, with direct events/distributed format enabled in both, exclusive capture 0/1, real RELEASE_CREDITS=0, planned slot/payload allocation and two-row reclaim enabled. It reuses fresh/held requests, partial/full forwarding, signed halfword/delayed STORE operand, held result/irrelevant update, full queue and stale response, MMIO/recovery. The full-head reuse point now allocates on the following edge, as production no-release requires. One two-lane memory bundle and simultaneous different-row LOAD response/STORE allocation check both complete words, original identities and occupancy. Every original write/data reference and certificate assertion passed. Exact frozen inputs/build/executable/log hashes are in reports/Tier_shared_LSQ_exclusive_capture_protocol_2026-10-09.json. This is one finite protocol sequence, not a whole CPU proof.

The next Tier2 profile keeps c85c56ea resources and policies and enables only this additional parameter. Commit/freeze once, run one original structural lint and one official PPA. Require area <=17997.018972010097 and Fmax >=355.67905522750954 before any CPU build/perf. Then IPC >=0.8561418961675636, unchanged instruction counts and case cycles <=8534/17439/162821/294021/6301/5592 before one array1 smoke. No acceptance or improved CPU metric is established by implementation or sample evidence. The older prepared Tier3 freeze is unmeasured and has not been sent to EDA.

## Terminal Tier2 result

The 4e707df9 freeze passed its one original structural lint and measured 17349.185832 um2 / 337.063858 MHz in one official PPA. It fails the historical 355.679055 MHz nonregression gate. Relative to c85c56ea it adds 13.107420 um2 and loses 6.791078 MHz, so the proposed timing improvement is not established. No CPU build/perf/smoke ran; IPC is unknown and accepted profiles remain intact. Reports/Tier2_shared_exclusive_capture_2026-10-09.json supersedes the dated running snapshot.

The worst path is now 2.907 ns from D-cache metadata row18 through LOAD response/report/CDB and actual allocation to the row0 qualified-word write tree and hold feedback. The allocation predicate still contributes to the combined write enable; splitting live/allocation data selection alone does not remove that hold-control path. No claim is made that the qualified bank universally improves timing. Sequential and SRAM areas are unchanged. This direct-dispatch Tier2 result does not measure the registered-dispatch Tier3 combination; measure one full current Tier3 integration before assuming the historical ALU path still dominates.
