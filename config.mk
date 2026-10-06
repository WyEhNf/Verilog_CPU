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
