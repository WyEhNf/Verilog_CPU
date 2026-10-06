# Fully expanded ASAP7 standard-cell area

Total: **37,020.923640 µm²**. Independent leaf-cell summation matches Yosys.

Mapped leaf instances: 346,368; unpriced leaves: 0; generic memories: 0.

Configuration: fe_width=2, be_width=2, phys_regs=48, rob_entries=16, rs_entries=4, lsq_entries=8, cache_stats_enabled=True, mul_impl=0, caches_enabled=True, predictor_enabled=True, fetch_queue_depth=16, completion_depth=8, shift_impl=0, phys_tag_impl=0, generation_width=8, checkpoint_impl=0, completion_bypass=False, serial_backend=False, int_issue_width=2, cdb_width=2, icache_mshrs=8, dcache_mshrs=4, dcache_lines=64.

All storage, including both cache data arrays, is implemented with standard cells. Hierarchy is retained for bounded-memory synthesis; every repeated instance is counted. Optional SAT memory-port priority/sharing optimizations are skipped, preserving original write priorities. This is the measured area of this mapping, not a minimum-area bound. Area excludes placement whitespace, clock-tree synthesis, physical timing repair, and routing. This run does not establish a new timing or IPC result.

| Module | Instances | Total own cell area (µm²) | Share |
|---|---:|---:|---:|
| rv32_dcache_nonblocking | 1 | 8,316.04 | 22.46% |
| rv32_icache_nonblocking | 1 | 6,194.09 | 16.73% |
| rv32_rob | 1 | 5,019.21 | 13.56% |
| rv32_branch_predictor | 2 | 4,494.28 | 12.14% |
| rv32_backend_joint | 1 | 2,805.91 | 7.58% |
| rv32_lsq | 1 | 2,775.52 | 7.50% |
| rv32_physical_register_file | 1 | 1,541.69 | 4.16% |
| rv32_reservation_station | 1 | 1,278.55 | 3.45% |
| rv32_completion_network | 1 | 1,243.60 | 3.36% |
| rv32_fetch_frontend | 1 | 1,172.47 | 3.17% |
| rv32m_multiplier | 1 | 561.17 | 1.52% |
| rv32i_alu | 2 | 547.92 | 1.48% |
| rv32m_divider | 1 | 409.79 | 1.11% |
| rv32_rename_unit | 1 | 352.14 | 0.95% |
| cpu_core | 1 | 147.04 | 0.40% |
| rv32_memory_bridge | 1 | 71.38 | 0.19% |
| rv32m_mdu_reservation_station | 1 | 57.39 | 0.16% |
| rv32im_decoder | 2 | 32.75 | 0.09% |

Sequential cell area: 14,635.112400 µm²; other cell area: 22,385.811240 µm².

Exact synthesis parameters and source hashes are recorded in `run_manifest.json`; per-stage command files are retained alongside the netlist.

Evidence: `run_manifest.json`, `synth.log`, `assemble.log`, `cpu_core_synth.v`, and `independent_area_audit.json` in the synthesis output directory.
