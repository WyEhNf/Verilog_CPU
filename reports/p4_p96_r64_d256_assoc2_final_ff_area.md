# Fully expanded ASAP7 standard-cell area

Total: **120,610.279800 µm²**. Independent leaf-cell summation matches Yosys.

Mapped leaf instances: 1,238,338; unpriced leaves: 0; generic memories: 0.

Configuration: fe_width=4, be_width=4, phys_regs=96, rob_entries=64, rs_entries=16, lsq_entries=16, cache_stats_enabled=True, mul_impl=0, caches_enabled=True, predictor_enabled=True, fetch_queue_depth=16, completion_depth=16, shift_impl=0, phys_tag_impl=0, generation_width=8, checkpoint_impl=0, completion_bypass=False, serial_backend=False, int_issue_width=4, cdb_width=4, icache_mshrs=8, dcache_mshrs=4, dcache_lines=256, dcache_index_hash=0, dcache_request_pipeline=0, dcache_ways=2, ram_size_bytes=268435456, legacy_sentinel_halt=0, icache_lines=64, icache_ways=2.

All storage, including both cache data arrays, is implemented with standard cells. Hierarchy is retained for bounded-memory synthesis; every repeated instance is counted. Optional SAT memory-port priority/sharing optimizations are skipped, preserving original write priorities. This is the measured area of this mapping, not a minimum-area bound. Area excludes placement whitespace, clock-tree synthesis, physical timing repair, and routing. This run does not establish a new timing or IPC result.

| Module | Instances | Total own cell area (µm²) | Share |
|---|---:|---:|---:|
| rv32_rob | 1 | 32,402.84 | 26.87% |
| rv32_dcache_nonblocking | 1 | 28,988.54 | 24.03% |
| rv32_backend_joint | 1 | 14,142.80 | 11.73% |
| rv32_branch_predictor | 4 | 8,988.57 | 7.45% |
| rv32_reservation_station | 1 | 8,782.03 | 7.28% |
| rv32_lsq | 1 | 7,286.59 | 6.04% |
| rv32_icache_nonblocking | 1 | 6,177.69 | 5.12% |
| rv32_physical_register_file | 1 | 5,121.31 | 4.25% |
| rv32_completion_network | 1 | 3,486.95 | 2.89% |
| rv32_fetch_frontend | 1 | 1,892.92 | 1.57% |
| rv32i_alu | 4 | 1,101.96 | 0.91% |
| rv32_rename_unit | 1 | 829.47 | 0.69% |
| rv32m_multiplier | 1 | 563.17 | 0.47% |
| rv32m_divider | 1 | 411.84 | 0.34% |
| cpu_core | 1 | 240.95 | 0.20% |
| MEMORY_SIZE=s32'00010000000000000000000000000000 | 1 | 70.83 | 0.06% |
| LEGACY_SENTINEL_HALT=s32'00000000000000000000000000000000 | 4 | 62.46 | 0.05% |
| rv32m_mdu_reservation_station | 1 | 59.36 | 0.05% |

Sequential cell area: 36,192.517200 µm²; other cell area: 84,417.762600 µm².

Exact synthesis parameters and source hashes are recorded in `run_manifest.json`; per-stage command files are retained alongside the netlist.

Evidence: `run_manifest.json`, `synth.log`, `assemble.log`, `cpu_core_synth.v`, and `independent_area_audit.json` in the synthesis output directory.
