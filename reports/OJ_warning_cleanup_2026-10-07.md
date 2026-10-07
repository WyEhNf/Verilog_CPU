# OJ compilation warning cleanup

The default submission profile now completes native Verilator 5.040 generation,
C++ compilation and linking with **zero warnings and zero errors**. Course
Verilator 5.020 generation also emits zero warnings. No additional `-Wno-*`
flags or `lint_off` directives were introduced. The existing course `-Wall
-Wno-fatal` flags remain in use.

| Check | Exit status | Warnings | Wall time |
| --- | ---: | ---: | ---: |
| Verilator 5.040 generation | 0 | 0 | 7.88 s |
| GCC 16.2 compilation, profile training and final link | 0 | 0 | 90.93 s |
| Total 5.040 generation and build | 0 | 0 | 98.81 s |
| Verilator 5.020 generation | 0 | 0 | 6.43 s |

The complete build uses the original course `scripts/sim.cpp`, tracing support,
assertions, the checked-in filelist, word simulation and the default host
profile. The validation ran directly on Windows. The local Windows time-symbol
compatibility object is a host toolchain workaround and is not shipped to OJ.
Full commands, versions, logs' warning counts, source hashes and measurements
are recorded in [the evidence JSON](OJ_warning_cleanup_2026-10-07.json).

## Source and configuration changes

- Split helper modules into files with matching names and update both filelists.
- Connect unused outputs to explicit unused wires and tie disabled recovery
  inputs to zero.
- Specify arithmetic operand/result widths and boolean parameter tests. Casts
  for parameterized queue counts retain their symbolic widths.
- Give functions automatic local storage, avoiding shared scratch state between
  ALU calls. Remove empty sequential controls and dead scratch assignments.
- Name generated blocks, distinguish shadowed variables and supply explicit
  hold defaults for count-update cases.
- Declare unused compatibility fields explicitly and scope feature-specific
  declarations to the corresponding generate branches.
- Set `CPU2026_COMPACT_IDS=0` in both the Make configuration and wrapper default,
  eliminating the `--protect-ids`/`--trace` conflict. The scheduling helpers
  accept original generated names and whitespace-wrapped assignments while
  retaining their exact field, reader-count and evaluation-boundary guards.
- Link with `-flto=2`, which bounds LTO workers and eliminates GCC's explicitly
  serial LTO warning. Other C++ compilation still uses one job.

The SRAM model has a recorded local change: its masked write is computed by an
automatic function before the original nonblocking array assignment. Its public
interface, supported configurations and clocked access timing are retained.
The `SYNTHESIS` interface branch is unchanged. The pinned upstream and local
hashes are distinguished in
[the framework manifest](../third_party/cpu2026-framework.json).

## Verification scope

One original basic input from problem 3201 completed with exit status 0, stdout
`5050` and **447 cycles**, matching the prior result. The limited 100,000-cycle
Pi execution is compiler profile training and is not a correctness pass.

The structural view also passed a Yosys hierarchy check with word simulation
disabled. That check emitted Yosys memory-lowering/port-resizing warnings; it
does not establish warning-free synthesis, area or timing. Historical unit
scripts that compile individual former module bundles may need to use the
updated filelists.

5.020 generation accepts the original-name scheduling helpers; both caches
pass their installation guards. 5.040 retains its conservative original
evaluator because its MDU boundary remains unrecognized. The 5.020 C++ build,
complete Pi execution, full correctness suite, IPC, area and frequency were
not rerun in this cleanup. Prior Pi and hardware measurements refer to their
older artifacts and are not new measurements of this source revision.

The supplied remote status-2 log stops in a warning prefix. Eliminating these
warnings does not identify the missing remote error tail or prove that its
underlying failure has been repaired.
