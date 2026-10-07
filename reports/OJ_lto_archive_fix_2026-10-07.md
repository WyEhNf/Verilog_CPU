# Repair the OJ LTO model link

The supplied OJ log identifies a final-link failure: Verilator 5.040 generation
and the GCC instrumentation build pass, but profile-use/LTO cannot resolve
`Vstudent_top`'s constructor, destructor, `eval_step()` and `final()` methods.
This is a host linking failure, before any correctness testcase runs.

The failure pattern matches an archive tool that cannot index GCC's LTO
intermediate objects. GCC documents the corresponding plugin/tool requirement
in [its LTO options](https://gcc.gnu.org/onlinedocs/gcc/Optimize-Options.html).
The remote archiver's plugin discovery has not been inspected directly.

Using the previously compiled real 5.040 model objects on native Windows,
forcing the archiver to lack an LTO plugin reproduced those same missing model
methods. Linking the same objects directly succeeded with zero warnings and
completed original OJ input 1 with output `5050`, **447 cycles**.

## Change

For the selected GCC PGO build, `tools/cpu2026_pgo.py` now replaces the generated
executable's `$(VM_PREFIX)__ALL.a` prerequisite with Verilator's complete
`$(VK_OBJS)` list. The existing `$^` link recipe receives model objects directly,
bypassing the archive index. User objects, runtime objects, libraries and flags
remain in the original recipe. No new archiver dependency is introduced.

The wrapper checks the expected makefile format before making this change and
records `model_linkage: direct objects`. Compilation remains serial, while LTO
retains its two-worker limit. PGO-disabled/custom-driver/non-GCC paths retain
the ordinary build. RTL and the course C++ driver are unchanged by this repair.

## Validation

| Check | Result |
| --- | --- |
| Forced missing-plugin archive, real model objects | Reproduced undefined `Vstudent_top` methods |
| Direct link of the same objects | Exit 0; zero warnings |
| Clean native Verilator 5.040 generation | Exit 0; zero warnings; 8.43 s |
| Complete GCC build, training and profile-use/LTO link | Exit 0; zero warnings; 88.27 s |
| Clean build total | **96.70 s** |
| Fresh binary, original OJ input 1 | Output 5050; 447 cycles; exit 0 |
| 5.020 generated makefile prerequisite format | Accepted; original link recipe retained |

The clean PGO build produced no model archive. Commands, versions, phase
statuses, source hashes and fault-reproduction diagnostics are in
[the evidence JSON](OJ_lto_archive_fix_2026-10-07.json).

These are native Windows results using the existing course-version tools.
The archive failure was simulated locally; the remote Nix environment was not
run. The Windows time-symbol compatibility object remains a local host
workaround. No full Pi execution, benchmark suite or new PPA measurements were
run. The repaired commit still requires a remote OJ submission to confirm its
result there.
