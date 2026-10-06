# JOIN-06 performance/area summary

ASAP7 blackbox logic area excludes unmapped `$mem_v2` arrays. The generated
genlib does not provide sign-off timing, so delay/fmax is intentionally reported
as unavailable rather than as a physical timing result.

| Config | Logic area (um2) | Area ratio | Geo. speedup | Speedup/area |
| --- | ---: | ---: | ---: | ---: |
| fe1_be1_p64_r32 | 26959.5135 | 1.0000 | 1.0000 | 1.0000 |
| fe2_be2_p64_r32 | 37324.8000 | 1.3845 | 1.2476 | 0.9012 |
| fe4_be4_p96_r64 | 113312.8294 | 4.2031 | 1.3766 | 0.3275 |

Per-program results:

| Config | Program | Cycles | IPC | Speedup |
| --- | --- | ---: | ---: | ---: |
| fe1_be1_p64_r32 | accumulate | 2558 | 0.164973 | 1.0000 |
| fe1_be1_p64_r32 | m_isa_smoke | 2083 | 0.050888 | 1.0000 |
| fe1_be1_p64_r32 | vmul | 1288 | 0.114130 | 1.0000 |
| fe1_be1_p64_r32 | vvadd | 1288 | 0.114130 | 1.0000 |
| fe2_be2_p64_r32 | accumulate | 2017 | 0.209222 | 1.2682 |
| fe2_be2_p64_r32 | m_isa_smoke | 1827 | 0.058019 | 1.1401 |
| fe2_be2_p64_r32 | vmul | 1001 | 0.146853 | 1.2867 |
| fe2_be2_p64_r32 | vvadd | 989 | 0.148635 | 1.3023 |
| fe4_be4_p96_r64 | accumulate | 1496 | 0.282086 | 1.7099 |
| fe4_be4_p96_r64 | m_isa_smoke | 1749 | 0.060606 | 1.1910 |
| fe4_be4_p96_r64 | vmul | 981 | 0.149847 | 1.3129 |
| fe4_be4_p96_r64 | vvadd | 959 | 0.153285 | 1.3431 |

The assignment's 1.3x speedup-at-area-growth gate is not marked complete by
this report. SRAM macro area and real STA are still required for final PPA.
