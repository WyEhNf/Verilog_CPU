# Tier3 clock-path analysis, 2026-10-09

This is an implementation review of `c2a09eaa`, not a new timing measurement.
The original sections were read-only snapshots. A default-off pending lookup implementation is recorded below; it has no new CPU PPA/IPC acceptance yet.
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
pending queue to be empty. The pending packet is injected into ROB completion while branch_pending is set.
Direct mode completes it on apply; staged mode can make it ready on preview,
but recovery_hold blocks its retirement through the descriptor/apply interval.
Apply clears the pending owner. Reset and whole flush also
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

## Default-off pending lookup implementation

ROB_RECOVERY_PENDING_OWNER is passed through the shared course top/core/backend to RECOVERY_CALLER_OWNED in the existing ROB. Mode zero retains both original live-query implementations and generic stale-input rejection. Mode one declares a private caller contract: only the backend's captured branch_pending may supply valid recovery lane 0, all other lanes remain zero. It replaces only that repeated row-valid/GEN query by tag-valid plus an explicit slot bound. Original relative age versus occupancy, oldest lane selection, destinations/checkpoints, reclaim/kill/epoch, full pending tag storage and all capture/preview/apply edges are unchanged. Both direct and staged recovery use the same policy implementation.

The initial ownership acquisition still uses branch_training_live's full valid/GEN query and accepts only an uncanceled ALU redirect. Ordinary producer construction excludes every redirecting ALU result. MDU, LSQ report and STORE ACK preserve their own different instruction identities. The producer contract has a simulation assertion rejecting an ordinary producer with the pending branch's complete tag. Every valid caller certificate also invokes a simulation-only original ROB live/generation reader and asserts its result; this is checked on the pre-edge of preview and apply, not merely at capture. None of these debug readers/registers creates synthesized state.

A necessary lifecycle clarification: the branch's recovery completion packet is injected whenever branch_pending is set, including a staged preview edge. Thus it may be ready before staged apply, contrary to the earliest wording of this review. It cannot retire in that interval: STAGED_RECOVERY's recovery_hold blocks commit and allocation from the first pending edge, and apply also suppresses ordinary commit. In direct mode, completion and apply share the first pending edge; captured branch readiness is zero before that edge. Optional backend recovery allocation credits may install new work against the retained prefix on direct apply, but cannot replace the branch row. The code comment was corrected accordingly. All pending/descriptor apply/reset/flush clears and existing failed-preview and matching-commit fallback clears are unchanged.

A finite paired shared-backend sample passed with BE2/ROB8/PHYS40/RS4/LSQ4, original versus caller-owned lookup in direct/staged modes. It exercises a delayed older load, older ordinary ALU completion, a redirect and younger instruction allocated together, retained ordered commits, row reuse with the original full generation, and reset/whole flush while an owner is pending. It compares each mode's pair of valid public packets, handshakes and ROB/allocator identity state. This is not a generic stale-input test with a fabricated certificate, and is not a whole CPU proof. No tier profile or running Tier1 source freeze enables this new policy yet; CPU area, frequency and IPC remain unmeasured for it.

The one passing finite sample finished at 532 ns: each mode observed three captures, three previews and one apply; the other two captures were explicitly canceled by whole flush and reset. Build/simulation elapsed 76.127277 s. Exact frozen input/executable/log hashes and the corrected pre-simulation fixture monitor error are retained in reports/Tier_shared_pending_recovery_owner_protocol_2026-10-09.json. No full CPU correctness suite or PPA was added for this policy.
