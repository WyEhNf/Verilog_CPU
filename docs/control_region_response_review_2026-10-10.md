# Complete region comparison and WORD response projection

The213-pin `03a4f3e9` prefix/held identity combination is rejected at36078.98157799465um2 /388.3200606750095MHz: it exceeds both area ceilings and regresses frequency. The previous212-pin `3a586c66` candidate remains the higher-frequency candidate inside the historical area ceiling at35861.85621799505um2 /393.99769141977686MHz, still unaccepted because500MHz fails and IPC/cycles are unknown. [213 terminal evidence](../reports/Tier3_shared_prefix_identity_2026-10-10.json).

Actual213 paths cross DCache metadata row38, LSQ response-source validity0.6353ns, direct response-query selection1.083ns and RS parallel-wake value distribution1.664ns before an anonymous FF at2.515ns. Near-worst paths cross ICache control-target selection1.106ns, control-query distribution1.450ns, way0/domain5 region match1.595ns and MSHR row4 line write2.346ns. Anonymous FF bit identities are not inferred. The new215-pin experiment retains all212 values, keeps rejected prefix/held queries0, and combines two new combinational projections targeting these actual serial query/format paths. It does not remeasure individual rejected policies.

## ICache complete upper-region equality before target selection

The original four JAL candidates, full32-bit arithmetic/unsigned comparison, outside-line predicate and preferred/first-word priority are unchanged. Those priority grants are onehot0 for arbitrary input instructions by their prefix construction. With one selected grant k, the original complete control target equals candidate k. With no grants, the original OR selector yields exactly0. Therefore, for the complete per-way region prefix P, equality to the selected target's upper R bits is exactly:

`OR(grants[k] AND (P == candidate[k].upper_R)) OR (no_grants AND P == 0)`.

The helper prepares all four complete region comparisons before late grants, then distributes the selected scalar equality to the existing query domains. The no-grant zero-target equality is retained, including invalid cycles. Native nonreset checks compare every domain view to the original complete selected target's upper-region comparison and check the original grants are onehot0. No new state, tag ownership, valid gate, request priority, epoch or MSHR edge is added.

Only the lower32-R target bits traverse the existing late control-query tree, because its consumers require set and complete stored low tag bits; the full upper region is checked by the independent exact predicate. Internal query-view upper padding changes intentionally, while the full control target, complete cache identity comparison, raw control-match vector and presence/public packets remain original. No tag bit is discarded. Guards require original region-tag/parallel/nonblocking cache policies and original complete low-tag geometry. Both helpers are present in both active source filelists.

The new region policy uses its production query logic under WORD_SIM, disabling the old whole-cache word-query shortcut for this policy. Original demand/prefetch/control semantics remain and original full-core structural lint without WORD_SIM follows the finite point.

## LSQ WORD merge/format before full response-row priority

The original response-row predicate retains every LSQ full generation, valid and response-wait check. The original response selector chooses the highest matching row, or row0 when no row matches, including arbitrary duplicate matches/invalid cycles. This always identifies one complete row. Thus formatting the selected row's WORD response equals selecting that same row's already-formatted response. Each row prepares the original byte-mask merge with its full32-bit saved forwarding data, current WORD data, original size and unsigned flag. All four byte-mask bits, size codes0..3 (2/3 retain original full word) and signed extension retain their original definitions.

The new32-bit formatted-value selector uses the original highest-match/default-row0 events. WORD input views are bounded to four-row domains. Arbitrary full-line responses take the original extraction/merge/format result unchanged; the CPU's actual word-response port permits unused line cones to prune. Native nonreset checks compare the complete raw response value to the original selected-metadata formatter on every edge, including invalid/flush cycles. The full response query/tag fields and all row state edges remain original; no response-ready/public packet/count/GEN/recovery change or new latency is introduced.

## One finite binary and staged gates

One finite binary combines actual BE2/ROB8/PHYS40/RS8/LSQ4 backend pairs in direct/staged recovery and direct/registered issue, differing only WORD preselection0/1. Prior carry range, invalid LSQ preload and original unpipelined MDU class are fixed in both. Prefix/held queries0, full decoded response source query1 and original circular recovery are fixed, with genuine response identity driving the existing source port. Public cycles/full packets, raw response value/matches and all20 raw LSQ metadata families/full generations are compared.

The same binary contains one genuine ICache128/ways2/MSHR8/region12/domain16 pair differing only region prequery0/1, with target-prefix/class-send fixed1. Original demand/control/sequential competition, held instruction replies, epoch redirect, stale ordinary/retained control return and demand error expectations remain. Complete raw control target/match vector/presence, public cycles/packets and MSHR lifecycle/identity are compared. No cache or queue state is forced.

Two tiny production-helper input probes add128 WORD merge/format points (16 masks/four sizes/both unsigned choices) and15 region points (no grant/all four onehot grants, three prefix pairs, matching/nonmatching/zero cases). No unrelated LSQ16 plan/range/reuse point is repeated. Coverage is bounded, not a full CPU, all geometries/operands or comprehensive cache correctness claim.

The initial finite attempt stops at compilation because the fixture counter used reserved identifier `matches`; no simulation runs. Frozen input hashes, compile log and failure are preserved in the original directory. Only that counter is renamed to `hit_count`; RTL and assertions are unchanged. The same finite point is compiled once in a fresh_r1 directory.

After finite PASS, commit/freeze215 numeric pins, run original full-core structural lint without WORD_SIM, then one official PPA. Strict area<=35891.672317998215 and F>=500 permit CPU build/six original performance cases. Original dynamic instructions, IPC>=1.1152626918348099 and every accepted cycle ceiling permit one array1 smoke. No individual-policy PPA sweep or broad correctness suite is planned. All new controls default0 in the shared parameterized CPU and canonical accepted profiles remain unchanged. Final500MHz/latest-source three-tier verification and IPC1.5/1GHz/unrestricted-area exploration remain outstanding.

## Finite result

The repaired same finite point passes in96.465152s; simulation completes2us in0.039s. Direct/staged backends observe140/157 nonreset edges and counts0/1/2, with raw response value/full match predicates and all20 metadata families/full GEN agreeing. The genuine ICache pair observes5 memory sends,3 replies,9 held reply edges, one three-class competition and one stale ordinary response check. The128 WORD format points and15 control-region points pass (5 region matches/25 misses across two ways). Frozen/current RTL/fixture/tool/Verilator hashes and preserved initial compile-failure hashes verify. [Exact finite evidence](../reports/Tier_shared_control_region_response_protocol_2026-10-10.json). No all-geometries/full CPU, IPC or PPA claim follows.
