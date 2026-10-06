# Fully expanded ASAP7 standard-cell area

Total: **145,371.785400 µm²**. Independent leaf-cell summation matches Yosys.

Mapped leaf instances: 1,505,983; unpriced leaves: 0; generic memories: 0.

Configuration: fe_width=4, be_width=4, phys_regs=96, rob_entries=64, rs_entries=16, lsq_entries=16, cache_stats_enabled=True, mul_impl=0, caches_enabled=True, predictor_enabled=True, fetch_queue_depth=16, completion_depth=16, shift_impl=0, phys_tag_impl=0, generation_width=8, checkpoint_impl=1, completion_bypass=False, serial_backend=False, int_issue_width=4, cdb_width=4, icache_mshrs=8, dcache_mshrs=4, dcache_lines=512, dcache_index_hash=1, dcache_request_pipeline=0, dcache_ways=2, ram_size_bytes=268435456, legacy_sentinel_halt=0, icache_lines=64, icache_ways=2.

All storage, including both cache data arrays, is implemented with standard cells. Hierarchy is retained for bounded-memory synthesis; every repeated instance is counted. Optional SAT memory-port priority/sharing optimizations are skipped, preserving original write priorities. This is the measured area of this mapping, not a minimum-area bound. Area excludes placement whitespace, clock-tree synthesis, physical timing repair, and routing. This run does not establish a new timing or IPC result.

| Module | Instances | Total own cell area (µm²) | Share |
|---|---:|---:|---:|
| rv32_dcache_nonblocking | 1 | 57,484.65 | 39.54% |
| rv32_backend_joint | 1 | 22,639.24 | 15.57% |
| rv32_rob | 1 | 20,171.79 | 13.88% |
| rv32_branch_predictor | 4 | 8,988.57 | 6.18% |
| rv32_reservation_station | 1 | 8,782.03 | 6.04% |
| rv32_lsq | 1 | 7,286.59 | 5.01% |
| rv32_icache_nonblocking | 1 | 6,177.69 | 4.25% |
| rv32_physical_register_file | 1 | 5,121.31 | 3.52% |
| rv32_completion_network | 1 | 3,486.95 | 2.40% |
| rv32_fetch_frontend | 1 | 1,892.92 | 1.30% |
| rv32i_alu | 4 | 1,101.96 | 0.76% |
| rv32_rename_unit | 1 | 829.47 | 0.57% |
| rv32m_multiplier | 1 | 563.17 | 0.39% |
| rv32m_divider | 1 | 411.84 | 0.28% |
| cpu_core | 1 | 240.95 | 0.17% |
| MEMORY_SIZE=s32'00010000000000000000000000000000 | 1 | 70.83 | 0.05% |
| LEGACY_SENTINEL_HALT=s32'00000000000000000000000000000000 | 4 | 62.46 | 0.04% |
| rv32m_mdu_reservation_station | 1 | 59.36 | 0.04% |

Sequential cell area: 43,173.421200 µm²; other cell area: 102,198.364200 µm².

Exact synthesis parameters and source hashes are recorded in `run_manifest.json`; per-stage command files are retained alongside the netlist.

Evidence: `run_manifest.json`, `synth.log`, `assemble.log`, `cpu_core_synth.v`, and `independent_area_audit.json` in the synthesis output directory.
