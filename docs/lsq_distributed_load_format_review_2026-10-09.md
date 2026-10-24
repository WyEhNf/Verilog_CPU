# Distributed LOAD capture formatting

## Measured path and scope

The compact metadata freeze 0bc24c2a failed frequency at 8996.258935 um2 / 292.822419 MHz. Its worst path reaches request_owner/forward_data_o[7] at 3.074 ns, then the formatted upper-sign NAND drives 16 consumers / 9.03 fF and takes 0.136 ns. Arrival at phased complete_value_mem[1][28] is 3.355 ns. The next candidate targets this measured late qualification/sign-extension segment. No measured area/frequency improvement is inferred before a new official PPA.

LSQ_DISTRIBUTED_LOAD_FORMAT is a default-zero boolean passed from the shared course top through cpu_core and rv32_backend_joint to the same LSQ. It does not select another CPU implementation. The new common combinational formatter owns no state. Resource sizes, tag width/full generation, request selection, CDB, architectural STORE admission, forwarding masks/priority, recovery and all clock edges stay unchanged. Existing profiles keep their default policy.

## Exact algebra

The original request owner already computes admitted_load from its exact flush/recovery/found/wait/load predicate. Its qualified forwarding word is admitted_load ? owner_forward_data : 0. It now also exposes that same scalar predicate; no independent authority or relaxed qualification is computed.

For each of the four size codes and either unsigned flag, format(0)=0. Therefore format(admitted_load ? raw : 0) = admitted_load ? format(raw) : 0, including invalid, waiting, flushed and recovery cycles. This is an exact combinational identity, not a private ownership invariant. The public qualified forwarding word and target/forward masks remain unchanged. Only the internal full-forward result formatter uses the raw word and qualifies its output. The partial-forward capture still uses the original qualified word. Memory-response formatting remains original.

Size 0 selects the low byte; size 1 selects the low halfword; both size 2 and size 3 preserve default full-word behavior. Upper sign is !unsigned && !size[1] && (size[0] ? raw[15] : raw[7]). Bits 8..15 select that sign only for byte size; bits 16..31 OR it with size[1]-qualified original bits. Sign, byte/word class and final admission are distributed in the existing bounded control-tree implementation, with at most eight result bits per final leaf. No constant inverter delay chains or area exemptions are introduced.

An original format_relative_value(fwd_data,size,unsigned) assertion compares all 32 bits on every nonreset edge, including invalid packet cycles. Existing direct-phase reference assertions compare every write edge and the complete selected word, preserving allocation/response/result/partial/STORE priority.

## Bounded validation and gates

Reuse one paired BE2/LSQ4 fixture with direct-phase events 1 in both instances and distributed format 0/1. Preserve existing fresh/held requests, partial/full forwarding, delayed STORE operand, held result/irrelevant update, full-generation row reuse/stale response, MMIO and recovery scenarios. Replace one existing delayed forwarding word LOAD with a signed halfword and check ffffccdd. Add sixteen standalone formatter points covering four size codes, signed/unsigned and qualified/unqualified with negative byte/half signs. This remains one finite sequence, not a correctness suite.

After that sample passes, commit and freeze one Tier1 candidate, run one original full-core structural lint and one official PPA. Require area <=9000 and Fmax >=300 before any build/perf. Then require IPC >=0.6000 and no case cycle regression from c2a09eaa before one array1 smoke. No canonical configuration is replaced by implementation or sample evidence. Current-source Tier2/Tier3 profiles remain unmeasured; the accepted historical results remain their baselines.

## Finite result

The paired sequence passed once. Frozen source/build/executable/log hashes are recorded in reports/Tier_shared_LSQ_distributed_load_format_protocol_2026-10-09.json. All request/completion comparisons, original full-format comparisons and direct-phase write references passed. No CPU metrics or canonical replacement follow from this sample.

## Terminal Tier1 acceptance

The 509377c4 freeze passed one original structural lint (6.878091 seconds, zero errors/latches/UNOPTFLAT), one official PPA (599.524668 seconds), one build, six official performance cases and one array1 smoke. Area is 8968.688155 um2; Fmax is 305.854241 MHz; geomean IPC is 0.6012842155901663. All six cycles and instruction counts exactly match the c2a09eaa IPC-passing reference. The same CPU source is accepted for this Tier1 profile. Full identities and hashes are in reports/Tier1_shared_verified_2026-10-09.json.

Area decreases 27.570780 um2 and frequency increases 13.031822 MHz versus the immediate rejected compact freeze. Sequential and SRAM area remain identical; total area reduction is combinational mapping. The new worst arrival is 3.208 ns / minimum period 3.26953125 ns and ends in LSQ selection-payload capture through forwarding coverage/request-fire; the previous sign-extension endpoint is no longer worst. The new formatter hierarchy reports 4.85514 um2. This local area is not the whole-design area delta. No current-source Tier2/Tier3 metric or 500 MHz claim follows.
