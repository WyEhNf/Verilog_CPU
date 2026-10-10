# Complete LSQ candidate folding into direct CDB selection

Status: default-off implementation, one finite sample and full original
structural lint pass; one official PPA is running, with no metric acceptance. This document records the transformation
and its exact obligations.
It establishes no new area, frequency, IPC, cycle count or accepted profile.
The completed216 experiment is rejected for frequency regression; its evidence
is [the terminal record](../reports/Tier3_shared_report_packet_prefix_2026-10-10.json).

## Current source evidence

The216 official result is35883.959498um2 /369.675090MHz. Its worst path crosses
LSQ response-source validity0.6581ns, head/saved packet choice1.107ns, CDB lane1
source1 direct selection1.665ns, LSQ allocation fire2.205ns and response-wait
ownership2.592ns, ending2.660ns. Near-worst generation endpoints are2.622ns.
The source1 anchor means this dependency can affect arbitration of another
producer, not just routing the LOAD data itself. Anonymous FF bits are not
inferred from identifiers in another mapping.

`rv32_completion_network` directly qualifies each producer using its already
selected full tag's valid bit and optional live-tag equality. Each lane then
compares the selected tag against its complete `direct_hold_tag`. These
comparisons qualify held-source masks, free lanes and source ranks. LSQ selects
head/saved tags before these comparisons. Thus folding only the final value
word would leave tag selection on the arbitration dependency.

The same network separately selects each complete producer payload. Its full
held tag is already captured from the direct metadata root, only on an original
selected-but-blocked offer. That capture is retained; there is no duplicate
encoded tag reader to remove. This source check corrects the preliminary
third optimization proposed before inspecting the capture block.

## Proposed combined transformation

The default-off `COMPLETION_LOAD_PACKET_FOLD` shared CPU policy covers these
related changes:

1. Export the original complete raw head and saved/held `{ROB tag, physical
   destination, value}` candidates from the shared LSQ. Keep the full public
   LSQ completion packet, identity queries, error/cancel/unretired fields and
   original head-choice bit unchanged.
2. Compare both complete candidate tags against optional live-tag filtering
   and each lane's full held tag before head/saved selection. Choose only the
   resulting scalar classifications after the original head-choice bit.
   Producer valid/target-live, exact held source, RR/ranks/ready and every state
   edge must retain their original expressions and meanings.
3. Fold the head/saved payload choice into the original direct source grant.
   Preserve common producer flags and every optional branch/store/address
   field. For the split LOAD source, route candidates under `grant & head` and
   `grant & !head`, instead of routing a wide head/saved mux and subsequently
   masking it by the CDB grant. Preserve the existing metadata-root tag capture,
   its selected-and-blocked event, invalid holds and reset/flush behavior.

For tags H,S and original choice h, each comparison obeys the unconditional
identity `((h ? H : S)==T) == (h ? (H==T) : (S==T))`. Likewise,
`grant & (h ? H : S)` equals `(grant & h & H) | (grant & !h & S)` bitwise.
These identities require no queue/window invariant, shortened generation,
ownership shortcut or fabricated validity certificate. Original full public
zeros on invalid cycles remain the reference for both scalar and payload
assertions.

The existing direct tag capture remains unchanged: metadata root capture on
selected-and-blocked offers, otherwise retained payload state. Compare full
held tags/sources/valid and RR state against the original finite point, and
retain native original payload and tag-class equality on all non-reset edges.

## Candidate selection and verification obligations

The216 range/whole-packet transformation removed the prior count-range path
from the five worst paths, but did not improve overall PPA. It is not accepted
on that basis. A combined packet-prefix plus complete CDB candidate-fold
experiment could remove its newly exposed dependency while retaining the
earlier range transformation. Such reuse needs the new structural change,
explicit combined evidence and strict final gates; do not remeasure216 alone
or run an individual-policy sweep. All other212 numeric values should remain
fixed, and rejected cache/response/independent held-query policies stay0.

Keep one parameterized backend and default-off behavior for unsupported modes.
Guard the fold for original direct completion mode2, complete head/saved
packets and identity prequeries. Preserve FIFO and legacy paths, optional
metadata geometry, all sources, all valid/full tags and every invalid-cycle
output. Do not specialize logic to benchmark values or lower the GEN width.

Use one finite binary with the existing paired backend stimulus, differing
only the combined CDB fold policy while packet prefix is fixed in both. Retain
the complete original packet/slot/range and full metadata assertions. Include
one small actual completion-network port stimulus covering source locks,
head/saved tags that differ in high generation bits, RR/blocked lanes and
reset/flush, with full raw outputs and state equality. Do not force queue
state, omit failed assertions or repeat unrelated LSQ16 packet probes.

After finite success, commit/freeze numeric pins and run one full original
structural lint without WORD_SIM and one official PPA. Strict area35891.672318
um2 and500MHz gates precede CPU build/perf; all six original instruction counts,
cycle ceilings and IPC1.115262692 precede one array1 smoke. Final latest-source
Tier1/2/3 validation remains necessary before attributing historical metrics
to a new release. Full goals1..5 remain active.

## Finite terminal result

A default-off complete LOAD candidate CDB fold prepares full tag eligibility/held comparisons before head/saved choice, and folds full candidate metadata/value selection into the original direct source grant. Original public packets, priority, full tag locks and state edges remain unchanged; existing direct metadata tag capture is retained. One paired backend plus14-edge actual direct-network finite binary passes on its first attempt, including10 held-lane observations and2 high-full-tag locks. Complete packet prefix1 is fixed in both sides; its previous isolated PPA remains rejected. Frozen/current source and result hashes verify. [Finite evidence](../reports/Tier_shared_completion_load_packet_fold_protocol_2026-10-10.json) does not establish PPA/IPC. The new combined candidate awaits one full structural lint and official PPA; canonical profiles are unchanged.

Elapsed compile plus simulation101.910194s; actual simulation2us /0.035s. Native original complete packet, full tag qualification/equality and direct selected payload shadows pass. Direct140/staged157 edges retain all original metadata and recovery checks. Standalone optional branch/store payloads exercise the widest complete packet; the actual backends exercise both omitted optional fields. No all-input/all-geometry or whole-CPU claim. No prior512-point prefix probe is repeated.

## Structural lint and live PPA

The217-pin `a2938851` complete LOAD candidate tag/payload fold combination is frozen with source/tool/library hashes verified. Full original structural lint without WORD_SIM passes in26.980539s with errors/latches/UNOPTFLAT=0. One official PPA is running under verified live runner/synth/Yosys processes. This dated running observation is not a metric result or500MHz acceptance. No CPU phases run; IPC/cycles are unknown. [Progress evidence](../reports/Tier3_shared_completion_load_packet_fold_progress_2026-10-10.json).
