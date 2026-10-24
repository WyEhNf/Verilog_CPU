# Review of the first shared Tier1 IPC pass

Freeze: `c2a09eaa`, directory
`F:/CPU2026TierRuns/tier1_shared_store_retire_20261009`.
Manifest SHA256:
`c97384c64cba50f386977adaac3f940f7f81ef56c5e5a10ae6f01afe15cc839c`.

IPC 0.6012842155901663 passes, but area 9555.824755000795 um² and
Fmax 236.3804247460757 MHz fail. Six answers/instruction counts passed;
no CPU correctness smoke was run. No accepted configuration was replaced.
The one PPA took 661.445286 seconds. Logic area is 8318.283660 um²
(2250.277200 sequential, 6068.006460 combinational); SRAM area is
1237.541095 um². These are measurements, not estimates for a later candidate.

## Timing evidence

The worst path starts at instruction SRAM `rd_out[99]` and ends at an LSQ
selection payload flip-flop. Selected nets from the original critical-path
JSON have these arrival times in ns:

| Signal | Arrival |
|---|---:|
| Instruction SRAM rdata[99] | 0.2309 |
| backend_rs1[4] | 1.5500 |
| preview_read_phys[4] | 1.8380 |
| d_replace_rs_demand[0] | 2.2530 |
| dcache_req_addr[1] | 2.7820 |
| LSQ raw_forward_mask[0] | 3.2600 |
| LSQ request owner valid | 3.3140 |
| dcache_req_mask[4] | 3.4840 |
| MMIO predicate | 3.6680 |
| dcache_req_ready | 3.8460 |
| selection payload write enable | 3.9800 |

The path does not justify arbitrarily inserting a latency stage: the IPC pass
has only 0.214% margin. It motivates separating incoming allocation offers
from queries for already-owned request packets.

## Candidate changes to review before another evaluation

1. **Move previous-write SRAM forwarding to PRF read ports.** Currently each
   nonzero row combines its raw SRAM word with the previous CDB word before
   the operand read tree. With 36 rows and two ports, forwarding at the ports
   would replace many row-wide muxes with two muxes and two full physical-ID
   comparisons. Current-cycle CDB forwarding must retain highest-lane priority.
   Crucially, saved store-address addition/classification must use the corrected
   previous-write value too, not merely the final `read_data_o`. Raw-output rows
   must be a default-off option, restricted to SRAM/local rows and the parallel
   read implementation until the generic read path is supported. P0, illegal
   indices, reset, consecutive writes and simultaneous allocation must retain
   their existing behavior. No area saving is measured yet.

2. **Classify MMIO for ready from saved request metadata.** Keep valid-qualified
   bus routing and ACK logic unchanged, as described in the Tier3 clock review.
   For the allocation-load request bypass, computing classification from the
   visible fresh packet would retain the incoming decode path. A fresh load
   offer is already forbidden whenever *any* old valid store exists. Thus a
   classifier based on the existing selection packet AND the reduction of
   `allocation_present_stores` can correctly return false for every fresh load,
   while preserving classification for valid ordinary store requests. This
   also prevents an invalid stale exit packet from misclassifying a fresh load.
   The optional request register needs classification of its own saved packet.
   Assert equivalence to the original predicate on every valid request.

3. **Keep forwarding queries on existing request metadata.** Fresh allocation
   requests are loads with no old valid stores, so they cannot forward and
   cannot have an unresolved older-store hazard. Existing request slot/address/
   size metadata can feed the forwarding query, while fresh requests explicitly
   use zero forwarding mask/data/hazard. Do not simply zero forwarding for all
   allocated loads or change ordinary load eligibility. Review every age,
   mask, formatting and forwarding-hold consumer before implementing this.
   This targets the measured new-address-to-forward-mask segment directly.

If further area is needed, store operand data and load completion data occupy
mutually exclusive row classes in LSQ. A shared 32-bit owner may be possible,
but allocation must dominate an old completion when a row is reused, current
load results must not be overwritten by irrelevant data-update events, and
store forwarding must retain its exact bytes. Production tags/metadata cannot
be narrowed to pay for the area budget.

These are reviewed directions, not implemented or validated optimizations.
Combine a meaningful area and timing change before another expensive PPA;
do not sweep small capacity/policy variations or run a correctness suite.
