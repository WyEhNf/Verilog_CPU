# Fully expanded ASAP7 standard-cell area

Total: **36,406.230840 µm²**. Independent leaf-cell summation matches Yosys.

Mapped leaf instances: 338,393; unpriced leaves: 0; generic memories: 0.

Configuration: fe_width=2, be_width=2, phys_regs=48, rob_entries=16, rs_entries=4, lsq_entries=8, cache_stats_enabled=True, mul_impl=0, caches_enabled=True, predictor_enabled=True, fetch_queue_depth=16, completion_depth=8, shift_impl=0, phys_tag_impl=0, generation_width=8, checkpoint_impl=0, completion_bypass=False, serial_backend=False, int_issue_width=2, cdb_width=2, icache_mshrs=8, dcache_mshrs=4, dcache_lines=64.

All storage, including both cache data arrays, is implemented with standard cells. Hierarchy is retained for bounded-memory synthesis; every repeated instance is counted. Optional SAT memory-port priority/sharing optimizations are skipped, preserving original write priorities. This is the measured area of this mapping, not a minimum-area bound. Area excludes placement whitespace, clock-tree synthesis, physical timing repair, and routing. This run does not establish a new timing or IPC result.

| Module | Instances | Total own cell area (µm²) | Share |
|---|---:|---:|---:|
| rv32_dcache_nonblocking | 1 | 8,316.04 | 22.84% |
| rv32_icache_nonblocking | 1 | 6,194.09 | 17.01% |
| rv32_rob | 1 | 4,951.38 | 13.60% |
| rv32_branch_predictor | 2 | 4,494.28 | 12.34% |
| rv32_backend_joint | 1 | 2,794.50 | 7.68% |
| rv32_lsq | 1 | 2,317.53 | 6.37% |
| rv32_physical_register_file | 1 | 1,541.69 | 4.23% |
| rv32_completion_network | 1 | 1,243.60 | 3.42% |
| rv32_reservation_station | 1 | 1,201.07 | 3.30% |
| rv32_fetch_frontend | 1 | 1,172.47 | 3.22% |
| rv32m_multiplier | 1 | 561.17 | 1.54% |
| rv32i_alu | 2 | 547.92 | 1.51% |
| rv32m_divider | 1 | 409.79 | 1.13% |
| rv32_rename_unit | 1 | 352.14 | 0.97% |
| cpu_core | 1 | 147.04 | 0.40% |
| rv32_memory_bridge | 1 | 71.38 | 0.20% |
| rv32m_mdu_reservation_station | 1 | 57.39 | 0.16% |
| rv32im_decoder | 2 | 32.75 | 0.09% |

Sequential cell area: 14,637.445200 µm²; other cell area: 21,768.785640 µm².

Exact synthesis parameters and source hashes are recorded in `run_manifest.json`; per-stage command files are retained alongside the netlist.

Evidence: `run_manifest.json`, `synth.log`, `assemble.log`, `cpu_core_synth.v`, and `independent_area_audit.json` in the synthesis output directory.
