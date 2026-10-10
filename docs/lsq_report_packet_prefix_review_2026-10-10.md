# Complete saved/held report packet prefix candidate

This is a default-off experiment in the existing parameterized shared LSQ,
backend and CPU. `LSQ_REPORT_PACKET_PREFIX_SELECT=1` changes combinational
selection of the complete saved load packet, its valid bit and physical slot.
It adds no register, latency, state update or independent held ROB lookup.
Canonical Tier1/2/3 profiles remain unchanged. No new PPA/IPC acceptance is
established by the implementation or its finite sample.

## Evidence and purpose

The212 candidate has area35861.856218um2 and frequency393.997691MHz, failing
the500MHz goal. Its five worst reported paths cross the full-count range,
range-qualified priority, wide saved identity packet, ROB live/completion
lookup and downstream allocation/metadata ownership. The215 cache/response
combination regresses to36041.627618um2 /373.450036MHz and is rejected. Its
new policies are disabled in this candidate. All212 numeric parameter values
are retained; the only enabled new policy is complete packet prefix selection.

The rejected213 candidate moved only the ordinary private identity query and
enabled an additional independent held ROB identity lookup. Its full public
packet still waited for the original range-qualified per-row grants. This
candidate keeps held identity query0 and changes the complete packet and slot
selection instead. These experiments do not isolate individual contributions.

## Exact transformation

For power-of-two LSQ depth N, circular age is `(row-head)&(N-1)`. The original
range is `age<count` with the complete count, including0,N and encodings above
N. Eligible saved rows keep the exact original valid/load/complete/not-reported
conditions. Select the minimum circular age among all these eligible rows
without range. A covered eligible row exists iff this minimum is covered.
Consequently, its complete packet can be read before range and zeroed at the
root if the minimum is outside the range. No queue/window invariant is used.

The existing saved identity tree now carries that complete raw minimum packet:
ROB tag and decoded bank query, full LSQ generation/slot tag, value, error,
physical destination, unretired and recovery-cancel bits. The existing general
report payload tree carries a complete raw held packet. Its per-row matching
keeps the original valid bit, physical slot and all generation bits; only range
is removed from this private packet read. At most one physical slot can match.
The original range-qualified held-live signal still decides whether this packet
may override the normal packet. When held-live is false, raw held data is
ignored, including a stale or excluded held identity. No generation shortening
or assumption about held state is allowed.

The final16-bit word choices apply the original held priority and complete
normal coverage. Saved packet zeros on invalid cycles are retained. The parent
keeps the existing original head-response choice, formatting and response
checks. Completion valid becomes `covered || original_fast_head_present`;
slot uses the original order held, head-fast, minimum saved, or head when no
completion exists. The raw minimum slot is encoded before count qualification.

All consumers of the saved root use the final qualified packet, including the
public prepared packet and shared ROB identity/bank query. The original full
ROB live/state/error/generation and recovery checks remain in the backend.
Request/response readiness, forwarding, ACKs, wake, allocation, occupancy,
validity, generations, report holds and accepted completion edges are unchanged.

## Verification and limits

Native non-synthesis assertions retain the complete original saved/held packet,
range-qualified priority, original valid and slot tournament. They compare on
every non-reset edge, including flush and invalid cycles, and check full held
matches are onehot0. These shadows are removed only by the ordinary synthesis
guard, not by simulator-only shortcuts in the production selection.

One finite binary pairs actual BE2/ROB8/PHYS40/RS8/LSQ4 backends under direct
and staged recovery and direct and registered issue. It retains the previous
real load/BNE wake, blocked completion/held report, STORE ACK, error, arithmetic
wrap, reset/flush/recovery stimulus and20 metadata-family checks. Raw complete
packet/valid/slot/full hold identity and ROB lookup results are also compared.
Both sides connect the original decoded response-source inputs. Only complete
packet prefix0/1 differs; held identity query remains0 on both sides.

The same binary contains one512-point LSQ16 raw packet/control sample across
all head/full-count encodings, empty/dense/sparse/single eligibility, live or
stale held generation with bit10 mismatched, excluded rows and head-fast
responses. Its independent oracle uses modular ages and complete89-bit packet
values. This does not cover all eligibility patterns, CPU programs or profiles.
No queue state is forced. No previous unrelated LSQ16 plan/reuse sample is
repeated. Follow finite success with one full original structural lint without
WORD_SIM, then one official PPA. CPU build/perf/smoke requires the strict area
and500MHz gates. Any failed combination remains an unaccepted experiment.

There is a real area/timing tradeoff: a held packet read and a final complete
packet choice replace the original per-row qualified choice. The implementation
alone proves neither area reduction nor500MHz timing; only the frozen official
PPA can establish those metrics.

## Finite terminal result

A default-off complete LSQ saved/held packet, valid and slot prefix candidate retains all212 numeric values, disables rejected cache/response and independent held-query combinations, and adds no register or latency. One paired backend/full-packet finite binary passes on its first attempt: direct140/staged157 edges and512 raw packet/control points, including complete11-bit generation mismatch, held/excluded rows and invalid defaults. Frozen and current source hashes verify. The source/fixture review and [finite evidence](../reports/Tier_shared_report_packet_prefix_protocol_2026-10-10.json) do not establish PPA or IPC; canonical accepted profiles remain unchanged. Next: one full original structural lint and one official PPA.

Elapsed compile plus simulation95.080276s; actual simulation2us /0.043s. Raw point coverage:96 live held,128 stale bit10 GEN,36 excluded nonempty candidates and256 fast-head points. Both backends retain count0/1/2 coverage, direct3 and staged5 genuine recovery windows. The finite point passes on the first compiled binary. No CPU or whole-profile metric claim.

## Structural lint and live PPA

The216-pin `ceaec537` complete report packet/valid/slot candidate is frozen with source/tool/library hashes verified. Full original structural lint without WORD_SIM passes in24.122355s with errors/latches/UNOPTFLAT=0. One official PPA is running under verified live runner/synth/Yosys processes; this is a dated running observation, not a PPA result or500MHz acceptance. No CPU phases run and IPC/cycles are unknown. [Progress evidence](../reports/Tier3_shared_report_packet_prefix_progress_2026-10-10.json).
