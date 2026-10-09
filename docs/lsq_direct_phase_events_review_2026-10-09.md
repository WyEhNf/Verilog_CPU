# Direct LSQ phased payload write events

## Measured reason

The previous 366f4726 frozen Tier1 candidate measured 8960.946175 um2 / 284.286507 MHz and was rejected for frequency. Its longest path starts at D-cache metadata, passes LOAD reporting/completion and ROB qualification into LSQ selection/byte forwarding, then captures the formatted forwarded value in the shared phased data owner. Mapped _115579_/QN is _001611_; an inverter drives complete_value_mem[3][16]. Minimum period is 3.517578125 ns, with data arrival 3.4696 ns. No CPU build/perf/smoke was run for that source.

The original phased owner chooses a forwarded or memory response result in a 32-bit result selector, then chooses that result in another 32-bit phase selector. STORE updates and allocation likewise pass a data selector before the phase selector. These nested payload qualifiers are on the measured path, while the retained register boundary is already needed for protocol correctness.

## Exact event composition

LSQ_PHASED_DIRECT_WRITE_EVENTS defaults to zero throughout the same core/backend/LSQ. It requires PHASED_DATA_OWNER=1. Mode zero keeps the original selectors. Mode one composes their original last-event priorities into a single 32-bit selector with 3*BE_WIDTH+3 events, ordered low to high:

1. STORE data updates and wakeups: original first 2*BE_WIDTH data events, still qualified by original valid/store row state.
2. LOAD partial forwarding capture: original forward event, qualified by valid/load row state.
3. LOAD forwarded result, then memory response result: the original two result events and values, qualified by valid/load row state.
4. Actual allocation lanes, in their original last-lane order: full incoming STORE word for a STORE, zero for a LOAD.

Original allocation events are the highest data-selector events and also the highest phase event. Replacing their nested data/class selection by each lane's complete allocation word preserves last-lane priority even if multiple events are presented. Actual allocator grants still select distinct row identities. Removing lower-priority duplicate allocation events does not change write enable: the direct allocation event remains present. If no allocation occurs, data selector membership is precisely its first 2*BE_WIDTH events. Result event 1 still beats event 0; result phase still beats forwarding capture; both still beat STORE updates. Simultaneous events keep the original priority rather than relying on a new mutual-exclusion assumption.

All original event guards, reset/flush/recovery handling, response full tag/GEN checks, byte masks, formatting, complete words, allocation priority and payload-owner clock edges are retained. No storage bits or queue capacity change. Original forwarding data admission qualification remains present. This changes only how the existing complete word is selected before its write edge.

Every simulation payload row computes the original composed selector in parallel. It asserts exact write-enable equivalence on every edge and exact complete 32-bit data whenever a write occurs. That original query/selector is simulation-only in direct mode. Existing overlap and allocation-class assertions also remain active. Independent nonphased LSQ owners are untouched.

## Evaluation boundary

Reuse one existing finite paired BE2/LSQ4 stimulus, varying direct events 0/1 while both use saved query, saved candidate state and the phased owner. Its fresh/held LOAD, partial/full forwarding, delayed STORE data, held result, irrelevant update, full-row reuse/stale response, MMIO and recovery cases compare public valid packets/cycles plus the production full write-edge/data assertions. RELEASE_CREDITS=2 is only this reuse fixture; production Tier1 remains zero. The sample is not a whole CPU proof or an independent Boolean mirror test.

The candidate configs/tier1_shared_direct_phase_events.json retains the STORE-route/MSHR-owner parameter profile, enables this direct selector, and leaves the separate pending-recovery optimization disabled. Run one structural full-core lint and one frozen official PPA; CPU build/perf only after area <=9000 and frequency >=300. Enforce IPC >=0.6000 and no case-cycle regression from c2a09eaa before one array1 smoke. No new CPU metrics or accepted-profile replacement are established by this implementation.
