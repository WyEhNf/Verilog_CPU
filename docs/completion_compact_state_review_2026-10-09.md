# Compact consumed completion metadata

## Measured reason

The 76bc5f42 mode-1 freeze improves Tier1 frequency from 290.578888 to 299.853587 MHz, but increases area from 8893.003375 to 9021.088675 um2. It fails both gates, missing frequency by 0.146413 MHz and exceeding area by 21.088675 um2. No build/perf/smoke was run. This follow-up targets replication introduced by the earlier current-table query rather than changing resource capacity or instruction cycles.

The mapped mode-1 candidate's two early LSQ three-bit state readers each report 3.4992 um2 including their own control subtrees. Their cost alone cannot explain or recover the full 128.085300 um2 total area increase: whole-design mapping also changes. Merely pruning two unconsumed size bits on LOAD/MDU is not sufficient evidence of a 21 um2 gain. The final compact variant additionally reuses size already captured in the ALU's complete result packet, allowing redundant ROB size payload storage/read logic to become unused where RS inline metadata is active. A new full PPA is still necessary; no predicted area gain is treated as measured.

## Source metadata contract

COMPLETION_SOURCE_STATE_QUERY remains the same parameter throughout the shared top/core/backend: 0 retains the original post-CDB table query, 1 retains the complete three-bit source query, and 2 selects only consumed source metadata. Both nonzero modes require direct completion. No alternative width-specific backend, storage owner, pipeline stage, tag width or resource capacity is added.

In mode 2 every completion source still performs the exact current load_error_mem query. It is not replaced by a zero flag or a private LOAD ownership certificate. The existing early head/saved/held LOAD candidate query/choice is retained; each candidate reads one error bit rather than three error/size bits. Fallback predecoded and raw-tag LOAD queries likewise retain their original identity and current error. MDU reads its current error with its original raw tag.

Only an ALU source can supply STORE class. An ALU already captures calc_mem_size=issue_mem_size_i together with its full result tag in its existing result word owner, and publishes exec_mem_size_o with that same retained result. Those inputs came from the instruction's original size metadata, either inline RS metadata or the legacy ROB issue table. Mode 2 uses that existing two-bit field for ALU sources. For a valid STORE result, its full ROB tag still passes the original live/generation checks; the row cannot be reused before ordinary completion is accepted. A fast STORE completed on actual D/LSQ allocation has store_without_agu set, so d_rs_need excludes its RS allocation; it creates no ALU completion copy. The ordinary producer loop itself still accepts every valid nonredirecting ALU STORE. A normal RS STORE remains dependent on that ordinary completion before retirement. The ALU holds the same tag/size packet until its original ready/cancel event. The scalar table's original allocation/clear/update ordering and all CDB/recovery clock edges stay intact.

Both normal and shifted recovery mask conversions remain gated by their original cdb_is_store source class and packet validity. MDU and LSQ report producers keep STORE class zero in actual producer construction, so their size bits can be zero without changing a consumed field. LOAD request/report formatting continues using its original LSQ size/unsigned metadata. No size is removed from any valid STORE, and the exact same-edge LOAD error contribution is unchanged.

Every simulation valid ROB writeback checks unique source ownership and exact current error equality against the original selected-tag query. Mode 1 also compares both size bits on every valid writeback, preserving its original three-bit contract. Mode 2 compares both size bits whenever the selected CDB packet is STORE, including a held CDB result. Another production assertion checks that the MDU and LSQ sources never acquire STORE class. These references are simulation-only; no new synthesized proof state is introduced.

## Bounded evaluation

Reuse the finite original-versus-new BE2/ROB8/PHYS40/RS4/LSQ4 backend stimulus, in direct/staged recovery, with source query 0/2. Enable RS inline metadata in both pairs. Replace one of the existing eight row-reuse ADDIs by an iterative MUL and require its actual source mask to be observed. Delayed older LOAD, ordinary ALU completion, branch capture/hold/apply, reset/whole flush, full row-generation reuse, SB/SH/SW requests with real ACKs, and head LOAD error/registered terminal record are retained. Compare valid public packets/cycles and ROB/allocator identity, original error/STORE-size assertions, exact three STORE masks/words and MDU source coverage. This is one finite protocol sequence, not a whole CPU/backend proof.

An intermediate compact variant already passed the same bounded sequence before ALU size reuse, but was not committed or sent to PPA; its old source freeze is retained separately. The final ALU-size reuse requires its own finite sample. Only after that passes should one committed Tier1 freeze undergo original structural lint and one official PPA. Require area <=9000 and Fmax >=300 without rounding into a pass, then one build/six-case perf. Enforce IPC >=0.6000 and every case cycle no larger than c2a09eaa before one array1 smoke. No canonical profile replacement or new CPU metrics are established by the implementation.

## Final bounded sample result

The final ALU-size-reuse sequence passed once. Exact frozen inputs/build/executable/simulation hashes and the retained earlier compact pass are recorded in reports/Tier_shared_completion_compact_state_protocol_2026-10-09.json. Direct/staged pairs each retained three captures, three previews and one apply; reset/whole flush canceled the other two pending owners. MDU source coverage and the original error/STORE-size comparisons were asserted. No CPU PPA/IPC acceptance follows from this sample.

## Fast STORE lifecycle wording correction

A later source recheck confirms that the ordinary producer loop does not filter ALU STORE packets by FAST_STORE_COMPLETE_ACTIVE. Its explicit exclusion is for redirecting branches and ordinary LOAD address results. The fast STORE ownership argument instead comes from actual D/LSQ allocation: store_without_agu publishes the fast completion only with lsq_alloc_fire and also removes that instruction from d_rs_need before RS allocation. This wording correction changes no RTL or frozen PPA inputs. The original per-valid-STORE size assertion remains the independent reference check.

## Terminal CPU PPA

The 0bc24c2a freeze measured 8996.258935 um2 / 292.822419 MHz in one official PPA (493.946667 seconds). Area passes by 3.741065 um2; frequency fails. Compared with mode 1, area decreases 24.829740 um2 but frequency decreases 7.031168 MHz. No build/perf/smoke ran and IPC is unknown. The dated running record remains historical; reports/Tier1_shared_completion_compact_state_2026-10-09.json is terminal evidence.

The worst path still crosses D-cache return, completion and ROB store admission before next LSQ selection/forwarding and phased result capture. The formatted upper sign node has 16 consumers, 9.03 fF, and 0.136 ns delay; arrival is 3.3550 ns. Endpoint _116365_/QN is _001767_; _060397_ drives complete_value_mem[1][28], verified in this mapped.v. This source policy is not promoted and establishes no current-source Tier2/Tier3 result.
