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
