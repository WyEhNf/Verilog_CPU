# Tier3 clock-path analysis, 2026-10-09

This is an implementation review of `c2a09eaa`, not a new timing measurement.
No policies described below are enabled or implemented by this document.
Tier1 PPA of its IPC-passing freeze is running independently. Tier2 remains
accepted only at its `5be74e01` freeze.

The historical A109 Tier3 timing report is at
`F:/CPU2026CourseRuns/ER1_A109_tier3_20261006/result/synth/opt/timing.rpt`.
It reports a recovery-tag path through the ROB live-generation query, LSQ
identity/recovery qualification, RS issue qualification and ALU result capture.
Another limiting route contains LSQ forwarding qualification and the exact
MMIO request predicate before cache ready. These observations do not establish
current-source timing or a 500 MHz pass. The goal needs a measured Fmax of at
least 500 MHz under the course timing model, including its setup constraints.

## Pending branch ownership

`branch_capture_match` requires `branch_training_live`, which checks the
allocated ROB row and its full generation. The pending packet retains its full
tag. The producer loop excludes **every redirecting ALU result** from ordinary
completion, so a captured redirecting branch cannot become ready or retire
through that route. There is only one pending recovery; capture requires the
pending queue to be empty. Recovery completion makes that branch ready on the
apply edge, and apply clears the pending owner. Reset and whole flush also
clear it. The new optional ordinary completion/commit bypass explicitly
excludes branches.

This suggests a caller-owned certificate could remove the *second* live-query
from the pending-tag path. It must retain the full tag and full generation
storage. Before implementing it, prove that no configuration can complete the
same branch through another route, that no recovery can remove its row while
the certificate remains set, and that staged/direct apply clear the certificate
before row reuse. A simulator assertion must check the original full live-query
whenever a certificate is used. The existing pending clear on failed preview
must be reviewed carefully; replacing it by an assertion without establishing
the invariant would be incorrect.

## MMIO ready classification

The current exact exit predicate is valid AND store AND address `0x80000000`
AND line mask `0x000f`. LSQ public store/mask outputs are qualified late by
request ownership. The selected request packet already contains load/store
class, address and relative mask before that final valid qualification.

A payload classification could select **ready only** from the selected store,
exact address and relative mask `0xf`. The address fixes the byte offset to
zero, making that relative mask equivalent to line mask `0x000f`. For the
optional request register, classification must come from that register's saved
packet rather than the currently selected LSQ row. On every valid request it
must equal the original predicate. Invalid ready values may differ.

All side effects, ACK capture and memory-bus routing must continue using the
original valid-qualified predicate. In particular, an invalid stale exit
payload can coexist with a valid normal cache refill/writeback transaction;
using its raw classification for bus routing would corrupt that transaction.
The nonblocking SRAM query's ready depends on its saved query, making the
payload-only ready selection plausible without an allocation feedback cycle.
Other cache modes still need review and an explicit supported-policy guard.

## LSQ load-to-ROB ownership delegation

Loads acquire their full ROB identity at actual dispatch. Their ALU address
execution is excluded from ordinary result completion. An unreported live load
therefore cannot have retired through a previous LSQ report. Full LSQ generation
checks remain essential for responses; reported rows, held reports, full-tag
row reuse and same-edge recovery need separate analysis. The current early
return wake already checks unreported/unretired membership and recovery cancel.

Delegating a completion's ROB ownership to an unreported LSQ row might remove
another repeated lookup. This is less mature than the two reviews above:
report arbitration, held identity, completion backpressure and error publication
all need a common invariant before any RTL change. Do not infer safety merely
from a valid LSQ row, since reported loads and committed stores can outlive their
ROB rows.

## Evaluation boundary

Use the same parameterized core/backend at every width. Leave a default-off
policy until its ownership argument and a short directed protocol sample are
ready. Combine changes that plausibly shorten the measured critical paths,
then run one frozen performance/PPA evaluation. Reject IPC, area or frequency
regression before the exploratory phase. Preserve the historical accepted
freezes, and do not attribute their numbers to later source revisions.

## Pending ownership lifecycle recheck at db75467c

This is a later read-only refinement while one Tier1 MMIO-admission PPA runs. No pending ownership policy has been implemented or enabled. Historical A109 timing is still not evidence of current 500 MHz operation.

The common backend drives ROB recovery validity only from its private `branch_pending` on lane 0; all higher recovery lanes are zero. Capture requires !reset, !flush, !branch_pending, accepted selected redirect validity/ready and branch_training_live. The latter checks the saved full ROB generation and valid row against the ALU tag. Only that capture writes the pending full tag/value/physical-destination/PC packet.

The producer construction rejects **every** `alu_exec_redirect_valid` result from ordinary completion, independent of early-redirect, capture-ready or capture-phase policy. Thus a redirect captured here has no ordinary completion copy that could make its ROB branch row ready. MDU, LOAD-report and STORE-ACK sources are distinct allocated instruction classes and preserve their original complete identities; they cannot legitimately complete this branch. Ordinary completion/commit bypass also excludes branches. The private pending queue blocks another branch capture.

ROB recovery selection separately tests candidate age against occupancy. Even a caller-ownership policy should preserve this age/range test and all selected-slot/destination, checkpoint, kill-mask and epoch machinery. The proposed optimization would remove only the repeated row-valid/full-generation lookup for an already captured owner, retaining all tag storage and initial full-generation checks.

Direct recovery previews and applies on the pending owner's edge. Staged recovery captures its saved slot/age/kill mask and holds allocation/commit between preview and apply (`recovery_hold_i` and the ROB guard), so a captured row cannot be reused while its descriptor remains pending. Backend descriptor validity and branch_pending both clear on the apply event. Reset and whole flush clear both validity owners. The existing fallback also clears branch_pending if no descriptor is present and ROB preview fails, and the explicit matching commit fallback clears it if the pending tag commits. These fallback paths must remain intact during any implementation; do not replace them by an assertion alone.

A default-off caller-owned recovery policy could let the ROB use the existing private branch_pending authority for lane 0 instead of another live/generation query. A simulator must still compute the original full lookup and assert it for every valid ownership-certificate use, including direct/staged preview and the pre-apply edge. The generic ROB's default behavior must continue rejecting arbitrary stale incoming recovery tags. Enabling the policy declares an internal caller contract; it should only be exposed by the shared backend with this private pending queue. It must never be inferred from an arbitrary tag's valid bit, used for LSQ load/store responses, or enabled for another recovery producer without its own proof.

Before any measured candidate, a bounded shared-backend sample should exercise capture/hold/apply, older completion around capture, direct and staged owner clearing, reset/whole flush and row reuse after apply, while checking the original full query whenever the certificate is used. Existing unit inventory contains `tb/unit/rv32_backend_joint_tb.v`; no new sample or whole correctness suite was run for this review. This lifecycle review is an implementation basis, not a whole CPU formal proof or measured IPC/frequency result.
