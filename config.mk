# Optional machine configuration. Command-line assignments take precedence.
# Set executables to a single path/name; use a wrapper script for extra arguments.
# Keep machine-specific absolute paths out of your OJ submission.

PYTHON ?= python3
CXX ?= g++
AR ?= ar
BUILD_MAKE ?= make

# Course hardware tools (Linux x86-64 / x86-64 WSL2).
# Set APPIMAGE= to use only native tools.
APPIMAGE ?= $(FRAMEWORK_DIR)/cpu2026-tools-x86_64.AppImage
# Without an AppImage, build uses Verilator on PATH (provided by OJ).
# Explicit overrides always win; an invalid override fails instead of falling back.
# Bound host compilation memory without modifying the official build scripts.
VERILATOR ?= $(FRAMEWORK_DIR)/tools/verilator_low_memory.py
JOBS ?= 1
export CPU2026_BUILD_APPIMAGE = $(APPIMAGE)
# Keep top-level AXI waveforms; omit internal arrays from the default build.
CPU2026_TRACE_DEPTH ?= 1
export CPU2026_TRACE_DEPTH
# Use CPU2026_TRACE_DEPTH=0 to restore full internal waveform visibility.
# Keep original C++ names: --protect-ids conflicts with the required --trace.
CPU2026_COMPACT_IDS ?= 0
export CPU2026_COMPACT_IDS
# The optional value 1 retains the old compact-name profile for non-trace builds.
# Combine small C++ files by source size, keeping hot/cold flags separate.
CPU2026_CPP_GROUP_BYTES ?= 2097152
export CPU2026_CPP_GROUP_BYTES
# Set CPU2026_CPP_GROUP_BYTES=0 to compile every generated file separately.
# Optimize simulator runtime while retaining bounded compilation jobs.
CPU2026_OPT_FAST ?= -O3
export CPU2026_OPT_FAST
# Use CPU2026_OPT_FAST=-Os and CPU2026_PGO=0 for the original compiler level.
# Train GCC hot-code branch profiles on a bounded original Pi window, then
# link model objects directly with at most two LTO workers. This avoids relying
# on ar's LTO-plugin discovery. Other C++ jobs remain serial. Custom builds keep
# the ordinary compiler path. CPU2026_PGO=0 disables this build optimization.
CPU2026_PGO ?= 1
export CPU2026_PGO
# Split acyclic selector arrays to avoid repeated combinational evaluation.
CPU2026_SPLIT_SCHEDULE ?= 1
export CPU2026_SPLIT_SCHEDULE
# Set CPU2026_SPLIT_SCHEDULE=0 to reproduce the previous generated schedule.
# Equivalent word expressions retain every original clock/register boundary.
# This macro is passed only to Verilator; synthesis uses the original structure.
CPU2026_WORD_SIM ?= 1
export CPU2026_WORD_SIM
# Set CPU2026_WORD_SIM=0 for the original structural simulation view.
# Equivalent native scalar bit scans for the word selectors.
CPU2026_NATIVE_BITS ?= 1
export CPU2026_NATIVE_BITS
# Set CPU2026_NATIVE_BITS=0 to retain the course runtime's scalar loops.
CPU2026_UNROLL_STMTS ?= 4096
export CPU2026_UNROLL_STMTS
# Larger experimental configurations may require CPU2026_UNROLL_STMTS=1000000.
# Reuse settled core calculations while the original iterative MDU advances.
# Every CPU clock and all performance counters are preserved.
CPU2026_STABLE_MDU ?= 1
export CPU2026_STABLE_MDU
# Set CPU2026_STABLE_MDU=0 to keep the unmodified generated evaluator.
# Reuse the input-combinational calculation between a full falling evaluation
# and its rising evaluation when every non-clock input is unchanged.
CPU2026_ICO_PAIR ?= 1
export CPU2026_ICO_PAIR
# Set CPU2026_ICO_PAIR=0 to retain the original input-region scheduling.
# Optional real executable override for the low-memory driver.
# export CPU2026_REAL_VERILATOR = /path/to/verilator
YOSYS ?=
ABC ?=
STA ?=
ASAP7_LIB ?=

# Example native setup:
# APPIMAGE =
# VERILATOR = /opt/verilator/bin/verilator
# YOSYS = /opt/yosys/bin/yosys
# ABC = /opt/yosys/bin/yosys-abc
# STA = /opt/opensta/bin/sta
# ASAP7_LIB = /opt/asap7/lib

# For systems without FUSE, uncomment to extract AppImages at launch:
# export APPIMAGE_EXTRACT_AND_RUN = 1

# Optional prebuilt simulator. When set, run/test/perf skip RTL compilation.
# test/perf require the CPU2026-OJ stdin/stdout protocol; perf also requires
# 'CPU2026 cycles=N' on stderr. run requires the framework's positional CLI.
# Plain make / make code always builds RTL; it never copies this simulator.
SIM ?=
# SIM = /absolute/path/to/my-simulator

# Other overrides accepted here or on the command line:
# JOBS = 4
# TESTCASES = /path/to/testcases
# FILELIST = verilog/filelist.f
# BUILD = build
# MODE = opt
# CLOCK_PERIOD_NS = 2.0
# SYNTH_OUT = build/synth
# MAX_CYCLES = 100000000
# LATENCY = 10
# WAVE = trace.vcd
# LOG = run.log
