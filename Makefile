SHELL := cmd.exe
.SHELLFLAGS := /C

.PHONY: join02-vlt join02-vlt-fast join02-vlt-build join03 join03-build join04 join05 join06-report reference-trace-build reference-trace-test doctor lint unit matrix join01 join02 join h01 h02 h03 h04 a01 a02 a03 a04 a05 a06 a07 b01 b02 b03 b04 b05 b06 b07 b08 b09 regression asap7-maplib synth synth-bb

ROOT := $(CURDIR)
OSS_CAD_ROOT ?= $(ROOT)/.deps/oss-cad-suite-install/oss-cad-suite
RV_ROOT ?= $(ROOT)/.deps/riscv-toolchain-install/xpack-riscv-none-elf-gcc-15.2.0-1
OSS_CAD_ROOT_WIN := $(subst /,\,$(OSS_CAD_ROOT))
ICARUS ?= $(OSS_CAD_ROOT)/bin/iverilog.exe
VVP ?= $(OSS_CAD_ROOT)/bin/vvp.exe
VERILATOR ?= $(OSS_CAD_ROOT)/bin/verilator_bin.exe
YOSYS ?= $(OSS_CAD_ROOT)/bin/yosys.exe
GTKWAVE ?= $(OSS_CAD_ROOT)/bin/gtkwave.exe
RISCV_PREFIX ?= $(RV_ROOT)/bin/riscv-none-elf-

OSS_ENV = set "VERILATOR_ROOT=$(OSS_CAD_ROOT_WIN)\share\verilator" && set "YOSYSHQ_ROOT=" && call "$(OSS_CAD_ROOT_WIN)\environment.bat" &&

# Synthesis configuration knobs.  CFG is only the output directory name;
# FE_WIDTH/BE_WIDTH/PHYS_REGS/ROB_ENTRIES/MUL_IMPL are the real parameters.
# Use distinct CFG names when comparing multiplier implementations.  Keep the
# libdir path in forward-slash form: yosys treats backslashes in script strings
# as escapes.
FE_WIDTH ?= 1
BE_WIDTH ?= 1
PHYS_REGS ?= 64
ROB_ENTRIES ?= 32
RS_ENTRIES ?= 8
LSQ_ENTRIES ?= 8
ENABLE_CACHE_STATS ?= 0
ENABLE_CACHES ?= 1
ENABLE_PREDICTOR ?= 1
FETCH_QUEUE_DEPTH ?= 16
COMPLETION_DEPTH ?= $(if $(filter 1,$(BE_WIDTH)),4,$(if $(filter 2,$(BE_WIDTH)),8,16))
MUL_IMPL ?= 0
SHIFT_IMPL ?= 0
CFG ?= fe$(FE_WIDTH)_be$(BE_WIDTH)_p$(PHYS_REGS)_r$(ROB_ENTRIES)
ASAP7_LIB_DIR ?= $(ROOT)/third_party/asap7/lib
RTL_FILELIST = rtl/filelist.f
RTL_FILES := $(strip $(file <$(RTL_FILELIST)))

doctor:
	@$(OSS_ENV) "$(ICARUS)" -V
	@$(OSS_ENV) "$(VERILATOR)" --version
	@$(OSS_ENV) "$(YOSYS)" --version
	@$(OSS_ENV) "$(GTKWAVE)" --version
	@"$(RISCV_PREFIX)gcc.exe" --version
	@"$(RISCV_PREFIX)objdump.exe" --version
	@"$(RISCV_PREFIX)objcopy.exe" --version
	@powershell -NoProfile -Command "& '$(RISCV_PREFIX)gcc.exe' -print-multi-lib | Select-String 'rv32i/ilp32|rv32im/ilp32'"
	@if not exist "$(ASAP7_LIB_DIR)\asap7sc7p5t_SEQ_RVT_TT_nldm_201020.lib" (echo ERROR: ASAP7 RVT TT liberty files missing under $(ASAP7_LIB_DIR); run the third_party/asap7 fetch step & exit /b 1)
	@echo ASAP7 RVT TT liberty: OK

lint:
	@$(OSS_ENV) "$(ICARUS)" -g2005 -Wall -I rtl -s cpu_core -o build/h00_lint.vvp -c $(RTL_FILELIST)
	@$(OSS_ENV) "$(ICARUS)" -g2005 -Wall -I rtl -s rv32im_defs_tb -o build/h01_defs_lint.vvp -c $(RTL_FILELIST) tb/unit/rv32im_defs_tb.v
	@$(OSS_ENV) "$(ICARUS)" -g2005 -Wall -I rtl -s h01_channel_tb -o build/h01_channel_lint.vvp -c $(RTL_FILELIST) tb/integration/h01_channel_tb.v
	@$(OSS_ENV) "$(VERILATOR)" --lint-only --language 1364-2005 -Wall -Wno-fatal -Irtl --top-module cpu_core -f $(RTL_FILELIST)
	@$(OSS_ENV) "$(VERILATOR)" --lint-only --language 1364-2005 -Wall -Irtl rtl/common/rv32im_tag_compare.v
	@$(OSS_ENV) "$(VERILATOR)" --lint-only --language 1364-2005 -Wall -Irtl rtl/common/rv32im_fifo.v
	@$(OSS_ENV) "$(VERILATOR)" --lint-only --language 1364-2005 -Wall -Irtl rtl/common/rv32im_skid_buffer.v
	@$(OSS_ENV) "$(VERILATOR)" --lint-only --language 1364-2005 -Wall -Irtl rtl/common/rv32im_prefix_alloc.v
	@$(OSS_ENV) "$(VERILATOR)" --lint-only --language 1364-2005 -Wall -Irtl rtl/common/rv32im_priority_select.v
	@$(OSS_ENV) "$(YOSYS)" -q -p "read_verilog -I rtl $(RTL_FILES); hierarchy -check -top cpu_core; check"
	@$(OSS_ENV) "$(YOSYS)" -q -p "read_verilog -I rtl rtl/common/rv32im_tag_compare.v; hierarchy -check -top rv32im_tag_compare; proc; check"
	@$(OSS_ENV) "$(YOSYS)" -q -p "read_verilog -I rtl rtl/common/rv32im_fifo.v; hierarchy -check -top rv32im_fifo; proc; memory; check"
	@$(OSS_ENV) "$(YOSYS)" -q -p "read_verilog -I rtl rtl/common/rv32im_skid_buffer.v; hierarchy -check -top rv32im_skid_buffer; proc; check"
	@$(OSS_ENV) "$(YOSYS)" -q -p "read_verilog -I rtl rtl/common/rv32im_prefix_alloc.v; hierarchy -check -top rv32im_prefix_alloc; proc; check"
	@$(OSS_ENV) "$(YOSYS)" -q -p "read_verilog -I rtl rtl/common/rv32im_priority_select.v; hierarchy -check -top rv32im_priority_select; proc; check"

unit:
	@if not "$(NAME)"=="h00" if not "$(NAME)"=="" (echo Unknown unit NAME=$(NAME) & exit /b 2)
	@$(OSS_ENV) "$(ICARUS)" -g2005 -Wall -I rtl -s cpu_core_h00_tb -o build/cpu_core_h00_tb.vvp -c $(RTL_FILELIST) tb/unit/cpu_core_h00_tb.v
	@$(OSS_ENV) "$(VVP)" -N build/cpu_core_h00_tb.vvp
	@$(OSS_ENV) "$(ICARUS)" -g2005 -Wall -I rtl -P cpu_core_h00_tb.ENABLE_CACHE_STATS=1 -s cpu_core_h00_tb -o build/cpu_core_h00_stats_tb.vvp -c $(RTL_FILELIST) tb/unit/cpu_core_h00_tb.v
	@$(OSS_ENV) "$(VVP)" -N build/cpu_core_h00_stats_tb.vvp
	@$(OSS_ENV) "$(ICARUS)" -g2005 -Wall -I rtl -s cpu_core_invalid_tb -P cpu_core_invalid_tb.FE_WIDTH=3 -o build/cpu_core_invalid_fe.vvp -c $(RTL_FILELIST) tb/unit/cpu_core_invalid_tb.v
	@$(OSS_ENV) "$(VVP)" -N build/cpu_core_invalid_fe.vvp | findstr /C:"ERROR: invalid FE_WIDTH" >NUL
	@$(OSS_ENV) "$(ICARUS)" -g2005 -Wall -I rtl -s cpu_core_invalid_tb -P cpu_core_invalid_tb.BE_WIDTH=3 -o build/cpu_core_invalid_be.vvp -c $(RTL_FILELIST) tb/unit/cpu_core_invalid_tb.v
	@$(OSS_ENV) "$(VVP)" -N build/cpu_core_invalid_be.vvp | findstr /C:"ERROR: invalid BE_WIDTH" >NUL
	@$(OSS_ENV) "$(ICARUS)" -g2005 -Wall -I rtl -s cpu_core_invalid_tb -P cpu_core_invalid_tb.PHYS_REGS=32 -o build/cpu_core_invalid_prf.vvp -c $(RTL_FILELIST) tb/unit/cpu_core_invalid_tb.v
	@$(OSS_ENV) "$(VVP)" -N build/cpu_core_invalid_prf.vvp | findstr /C:"ERROR: invalid PHYS_REGS" >NUL
	@$(OSS_ENV) "$(ICARUS)" -g2005 -Wall -I rtl -s cpu_core_invalid_tb -P cpu_core_invalid_tb.ROB_ENTRIES=3 -o build/cpu_core_invalid_rob.vvp -c $(RTL_FILELIST) tb/unit/cpu_core_invalid_tb.v
	@$(OSS_ENV) "$(VVP)" -N build/cpu_core_invalid_rob.vvp | findstr /C:"ERROR: invalid ROB_ENTRIES" >NUL

matrix:
	@$(OSS_ENV) "$(ICARUS)" -g2005 -Wall -I rtl -s cpu_core_matrix_tb -o build/cpu_core_matrix_tb.vvp -c $(RTL_FILELIST) tb/unit/cpu_core_matrix_tb.v
	@$(OSS_ENV) "$(VVP)" -N build/cpu_core_matrix_tb.vvp

join01:
	@$(OSS_ENV) "$(ICARUS)" -g2005 -Wall -I rtl -s cpu_core_join01_tb -o build/cpu_core_join01_tb.vvp -c $(RTL_FILELIST) tb/models/rv32im_memory_model.v tb/unit/cpu_core_join01_tb.v
	@$(OSS_ENV) "$(VVP)" -N build/cpu_core_join01_tb.vvp | findstr /C:"PASS: JOIN-01"

join02:
	@$(OSS_ENV) "$(ICARUS)" -g2005 -Wall -I rtl -P cpu_core_image_tb.ENABLE_CACHES=$(ENABLE_CACHES) -P cpu_core_image_tb.ENABLE_PREDICTOR=$(ENABLE_PREDICTOR) -P cpu_core_image_tb.FETCH_QUEUE_DEPTH=$(FETCH_QUEUE_DEPTH) -P cpu_core_image_tb.COMPLETION_DEPTH=$(COMPLETION_DEPTH) -P cpu_core_image_tb.MUL_IMPL=$(MUL_IMPL) -P cpu_core_image_tb.SHIFT_IMPL=$(SHIFT_IMPL) -s cpu_core_image_tb -o build/cpu_core_image_tb.vvp -c $(RTL_FILELIST) tb/models/rv32im_memory_model.v tb/integration/cpu_core_image_tb.v
	@$(OSS_ENV) powershell -NoProfile -ExecutionPolicy Bypass -File tools/run_join02.ps1 -Vvp "$(VVP)" -Simulation build/cpu_core_image_tb.vvp -Manifest tests/manifest -ImageRoot RISC-V-CPU-Simulator/testcases

# Fast full-system regression: Verilator-compiled cpu_core_image_tb.
# --timing keeps the tb #5 clock and #12 reset delays; --debug makes the
# deep hierarchical references in the tb $display diagnostics visible.
join02-vlt-build:
	@if not exist "build\vlt" mkdir "build\vlt"
	@$(OSS_ENV) powershell -NoProfile -ExecutionPolicy Bypass -File tools/build_join02_verilator.ps1 -Verilator "$(VERILATOR)" -VerilatorRoot "$(OSS_CAD_ROOT)/share/verilator" -CompilerBin "$(ROOT)/../mingw64/bin"

join02-vlt: join02-vlt-build
	@$(OSS_ENV) powershell -NoProfile -ExecutionPolicy Bypass -File tools/run_join02.ps1 -Executable build/vlt/obj_dir/cpu_core_image_vlt.exe -Manifest tests/manifest -ImageRoot RISC-V-CPU-Simulator/testcases

# Fast regression: same image gate minus pi (pi alone costs ~30 min).
# qsort/tak/superloop/queens still cover branch/recursion/load-store paths.
join02-vlt-fast: join02-vlt-build
	@$(OSS_ENV) powershell -NoProfile -ExecutionPolicy Bypass -File tools/run_join02.ps1 -Executable build/vlt/obj_dir/cpu_core_image_vlt.exe -Manifest tests/manifest -ImageRoot RISC-V-CPU-Simulator/testcases -Skip pi

join03-build:
	@python tools/run_join03.py --build-only --report build/join03/build_report.json --cc "$(RISCV_PREFIX)gcc.exe" --objdump "$(RISCV_PREFIX)objdump.exe" --objcopy "$(RISCV_PREFIX)objcopy.exe" --readelf "$(RISCV_PREFIX)readelf.exe"

join03:
	@$(OSS_ENV) "$(ICARUS)" -g2005 -Wall -I rtl -P cpu_core_image_tb.ENABLE_CACHES=$(ENABLE_CACHES) -P cpu_core_image_tb.ENABLE_PREDICTOR=$(ENABLE_PREDICTOR) -P cpu_core_image_tb.FETCH_QUEUE_DEPTH=$(FETCH_QUEUE_DEPTH) -P cpu_core_image_tb.COMPLETION_DEPTH=$(COMPLETION_DEPTH) -P cpu_core_image_tb.MUL_IMPL=$(MUL_IMPL) -P cpu_core_image_tb.SHIFT_IMPL=$(SHIFT_IMPL) -s cpu_core_image_tb -o build/cpu_core_image_tb.vvp -c $(RTL_FILELIST) tb/models/rv32im_memory_model.v tb/integration/cpu_core_image_tb.v
	@$(OSS_ENV) python tools/run_join03.py --cc "$(RISCV_PREFIX)gcc.exe" --objdump "$(RISCV_PREFIX)objdump.exe" --objcopy "$(RISCV_PREFIX)objcopy.exe" --readelf "$(RISCV_PREFIX)readelf.exe" --vvp "$(VVP)" --simulation build/cpu_core_image_tb.vvp --config fe1_be1_p64_r32

# JOIN-04 proves that the same full-system path executes with real two- and
# four-wide decode/rename/dispatch/issue/commit configurations.
join04: join03-build
	@$(OSS_ENV) "$(ICARUS)" -g2005 -Wall -I rtl -P cpu_core_image_tb.FE_WIDTH=2 -P cpu_core_image_tb.BE_WIDTH=2 -P cpu_core_image_tb.PHYS_REGS=64 -P cpu_core_image_tb.ROB_ENTRIES=32 -P cpu_core_image_tb.RS_ENTRIES=8 -P cpu_core_image_tb.LSQ_ENTRIES=8 -P cpu_core_image_tb.MUL_IMPL=$(MUL_IMPL) -s cpu_core_image_tb -o build/cpu_core_image_tb_w2.vvp -c $(RTL_FILELIST) tb/models/rv32im_memory_model.v tb/integration/cpu_core_image_tb.v
	@$(OSS_ENV) python tools/run_join03.py --cc "$(RISCV_PREFIX)gcc.exe" --objdump "$(RISCV_PREFIX)objdump.exe" --objcopy "$(RISCV_PREFIX)objcopy.exe" --readelf "$(RISCV_PREFIX)readelf.exe" --vvp "$(VVP)" --simulation build/cpu_core_image_tb_w2.vvp --report build/join03/report_w2.json --config fe2_be2_p64_r32
	@$(OSS_ENV) "$(ICARUS)" -g2005 -Wall -I rtl -P cpu_core_image_tb.FE_WIDTH=4 -P cpu_core_image_tb.BE_WIDTH=4 -P cpu_core_image_tb.PHYS_REGS=96 -P cpu_core_image_tb.ROB_ENTRIES=64 -P cpu_core_image_tb.RS_ENTRIES=16 -P cpu_core_image_tb.LSQ_ENTRIES=16 -P cpu_core_image_tb.MUL_IMPL=$(MUL_IMPL) -s cpu_core_image_tb -o build/cpu_core_image_tb_w4.vvp -c $(RTL_FILELIST) tb/models/rv32im_memory_model.v tb/integration/cpu_core_image_tb.v
	@$(OSS_ENV) python tools/run_join03.py --cc "$(RISCV_PREFIX)gcc.exe" --objdump "$(RISCV_PREFIX)objdump.exe" --objcopy "$(RISCV_PREFIX)objcopy.exe" --readelf "$(RISCV_PREFIX)readelf.exe" --vvp "$(VVP)" --simulation build/cpu_core_image_tb_w4.vvp --report build/join03/report_w4.json --config fe4_be4_p96_r64

join05: join03-build
	@$(OSS_ENV) python tools/run_join05.py --iverilog "$(ICARUS)" --vvp "$(VVP)"

join06-report:
	@python tools/run_join06.py

reference-trace-build:
	@python tools/reference_trace.py --build

reference-trace-test:
	@python tools/test_reference_trace.py

join: join01 join02

h01:
	@$(OSS_ENV) "$(ICARUS)" -g2005 -Wall -I rtl -s rv32im_defs_tb -o build/rv32im_defs_tb.vvp -c $(RTL_FILELIST) tb/unit/rv32im_defs_tb.v
	@$(OSS_ENV) "$(VVP)" -N build/rv32im_defs_tb.vvp
	@$(OSS_ENV) "$(ICARUS)" -g2005 -Wall -I rtl -s h01_channel_tb -o build/h01_channel_tb.vvp -c $(RTL_FILELIST) tb/integration/h01_channel_tb.v
	@$(OSS_ENV) "$(VVP)" -N build/h01_channel_tb.vvp

h02:
	@$(OSS_ENV) "$(ICARUS)" -g2005 -Wall -I rtl -P rv32im_common_tb.LANES=1 -s rv32im_common_tb -o build/h02_lanes1.vvp -c $(RTL_FILELIST) tb/unit/rv32im_common_tb.v
	@$(OSS_ENV) "$(VVP)" -N build/h02_lanes1.vvp
	@$(OSS_ENV) "$(ICARUS)" -g2005 -Wall -I rtl -P rv32im_common_tb.LANES=2 -s rv32im_common_tb -o build/h02_lanes2.vvp -c $(RTL_FILELIST) tb/unit/rv32im_common_tb.v
	@$(OSS_ENV) "$(VVP)" -N build/h02_lanes2.vvp
	@$(OSS_ENV) "$(ICARUS)" -g2005 -Wall -I rtl -P rv32im_common_tb.LANES=4 -s rv32im_common_tb -o build/h02_lanes4.vvp -c $(RTL_FILELIST) tb/unit/rv32im_common_tb.v
	@$(OSS_ENV) "$(VVP)" -N build/h02_lanes4.vvp

h03:
	@powershell -NoProfile -Command "$$env:RISCV_PREFIX='$(RISCV_PREFIX)'; python tools/make_image.py tests/programs/accumulate.c --arch rv32i --out-dir build/images/accumulate-rv32i --cc '$(RISCV_PREFIX)gcc.exe' --objdump '$(RISCV_PREFIX)objdump.exe' --objcopy '$(RISCV_PREFIX)objcopy.exe' --readelf '$(RISCV_PREFIX)readelf.exe'"
	@powershell -NoProfile -Command "python tools/test_image_pipeline.py build/images/accumulate-rv32i/accumulate.image"
	@$(OSS_ENV) "$(ICARUS)" -g2005 -Wall -I rtl -s rv32im_memory_model_tb -o build/rv32im_memory_model_tb.vvp tb/models/rv32im_memory_model.v tb/unit/rv32im_memory_model_tb.v
	@$(OSS_ENV) "$(VVP)" -N build/rv32im_memory_model_tb.vvp
	@$(OSS_ENV) "$(ICARUS)" -g2005 -Wall -I rtl -s rv32im_memory_image_tb -o build/rv32im_memory_image_tb.vvp tb/models/rv32im_memory_model.v tb/unit/rv32im_memory_image_tb.v
	@$(OSS_ENV) "$(VVP)" -N build/rv32im_memory_image_tb.vvp +IMAGE=RISC-V-CPU-Simulator/testcases/naive.data

h04:
	@powershell -NoProfile -Command "python tools/test_trace_tools.py"

a01:
	@$(OSS_ENV) "$(ICARUS)" -g2005 -Wall -I rtl -s rv32im_decoder_tb -o build/a01_decoder.vvp -c $(RTL_FILELIST) tb/unit/rv32im_decoder_tb.v
	@$(OSS_ENV) "$(VVP)" -N build/a01_decoder.vvp | findstr /C:"PASS: A-01 decoder"
	@$(OSS_ENV) "$(VERILATOR)" --lint-only --language 1364-2005 -Wall -Irtl rtl/rv32im_decoder.v
	@$(OSS_ENV) "$(YOSYS)" -q -p "read_verilog -I rtl rtl/rv32im_decoder.v; hierarchy -check -top rv32im_decoder; proc; check"

a02:
	@$(OSS_ENV) "$(ICARUS)" -g2005 -Wall -I rtl -s rv32_branch_predictor_tb -o build/a02_predictor.vvp -c $(RTL_FILELIST) tb/unit/rv32_branch_predictor_tb.v
	@$(OSS_ENV) "$(VVP)" -N build/a02_predictor.vvp | findstr /C:"PASS: A-02 bimodal predictor and BTB"
	@$(OSS_ENV) "$(VERILATOR)" --lint-only --language 1364-2005 -Wall -Irtl rtl/predictor/rv32_branch_predictor.v
	@$(OSS_ENV) "$(YOSYS)" -q -p "read_verilog -I rtl rtl/predictor/rv32_branch_predictor.v; hierarchy -check -top rv32_branch_predictor; proc; memory; check"

a03:
	@$(OSS_ENV) "$(ICARUS)" -g2005 -Wall -I rtl -s rv32_icache_tb -o build/a03_icache.vvp -c $(RTL_FILELIST) tb/models/rv32im_memory_model.v tb/unit/rv32_icache_tb.v
	@$(OSS_ENV) "$(VVP)" -N build/a03_icache.vvp | findstr /C:"PASS: A-03 I-cache"
	@$(OSS_ENV) "$(VERILATOR)" --lint-only --language 1364-2005 -Wall -Irtl rtl/cache/rv32_icache.v
	@$(OSS_ENV) "$(YOSYS)" -q -p "read_verilog -I rtl rtl/cache/rv32_icache.v; hierarchy -check -top rv32_icache; proc; memory; check"

a04:
	@$(OSS_ENV) "$(ICARUS)" -g2005 -Wall -I rtl -P rv32_fetch_frontend_tb.FE_WIDTH=1 -s rv32_fetch_frontend_tb -o build/a04_frontend_fe1.vvp -c $(RTL_FILELIST) tb/unit/rv32_fetch_frontend_tb.v
	@$(OSS_ENV) "$(VVP)" -N build/a04_frontend_fe1.vvp | findstr /C:"PASS: A-04 frontend FE_WIDTH=1"
	@$(OSS_ENV) "$(ICARUS)" -g2005 -Wall -I rtl -P rv32_fetch_frontend_tb.FE_WIDTH=2 -s rv32_fetch_frontend_tb -o build/a04_frontend_fe2.vvp -c $(RTL_FILELIST) tb/unit/rv32_fetch_frontend_tb.v
	@$(OSS_ENV) "$(VVP)" -N build/a04_frontend_fe2.vvp | findstr /C:"PASS: A-04 frontend FE_WIDTH=2"
	@$(OSS_ENV) "$(ICARUS)" -g2005 -Wall -I rtl -P rv32_fetch_frontend_tb.FE_WIDTH=4 -s rv32_fetch_frontend_tb -o build/a04_frontend_fe4.vvp -c $(RTL_FILELIST) tb/unit/rv32_fetch_frontend_tb.v
	@$(OSS_ENV) "$(VVP)" -N build/a04_frontend_fe4.vvp | findstr /C:"PASS: A-04 frontend FE_WIDTH=4"
	@$(OSS_ENV) "$(VERILATOR)" --lint-only --language 1364-2005 -Wall -Irtl rtl/frontend/rv32_fetch_frontend.v
	@$(OSS_ENV) "$(YOSYS)" -q -p "read_verilog -I rtl rtl/frontend/rv32_fetch_frontend.v; hierarchy -check -top rv32_fetch_frontend; proc; memory; check"

a05:
	@$(OSS_ENV) "$(ICARUS)" -g2005 -Wall -I rtl -s rv32_dcache_tb -o build/a05_dcache.vvp -c $(RTL_FILELIST) tb/models/rv32im_memory_model.v tb/unit/rv32_dcache_tb.v
	@$(OSS_ENV) "$(VVP)" -N build/a05_dcache.vvp | findstr /C:"PASS: A-05 D-cache"
	@$(OSS_ENV) "$(VERILATOR)" --lint-only --language 1364-2005 -Wall -Irtl rtl/cache/rv32_dcache.v
	@$(OSS_ENV) "$(YOSYS)" -q -p "read_verilog -I rtl rtl/cache/rv32_dcache.v; hierarchy -check -top rv32_dcache; proc; check"

a06:
	@$(OSS_ENV) "$(ICARUS)" -g2005 -Wall -I rtl -s rv32_memory_bridge_tb -o build/a06_memory_bridge.vvp -c $(RTL_FILELIST) tb/models/rv32im_memory_model.v tb/unit/rv32_memory_bridge_tb.v
	@$(OSS_ENV) "$(VVP)" -N build/a06_memory_bridge.vvp | findstr /C:"PASS: A-06 memory bridge"
	@$(OSS_ENV) "$(ICARUS)" -g2005 -Wall -I rtl -s rv32_cache_stats_tb -o build/a06_cache_stats.vvp -c $(RTL_FILELIST) tb/unit/rv32_cache_stats_tb.v
	@$(OSS_ENV) "$(VVP)" -N build/a06_cache_stats.vvp | findstr /C:"PASS: A-06 cache statistics"
	@$(OSS_ENV) "$(VERILATOR)" --lint-only --language 1364-2005 -Wall -Irtl rtl/memory/rv32_memory_bridge.v
	@$(OSS_ENV) "$(VERILATOR)" --lint-only --language 1364-2005 -Wall -Irtl rtl/cache/rv32_cache_stats.v
	@$(OSS_ENV) "$(YOSYS)" -q -p "read_verilog -I rtl rtl/memory/rv32_memory_bridge.v; hierarchy -check -top rv32_memory_bridge; proc; check"
	@$(OSS_ENV) "$(YOSYS)" -q -p "read_verilog -I rtl rtl/cache/rv32_cache_stats.v; hierarchy -check -top rv32_cache_stats; proc; check"

a07:
	@$(OSS_ENV) "$(ICARUS)" -g2005 -Wall -I rtl -s a07_frontend_cache_tb -o build/a07_frontend_cache.vvp -c $(RTL_FILELIST) tb/models/rv32im_memory_model.v tb/integration/a07_frontend_cache_tb.v
	@$(OSS_ENV) "$(VVP)" -N build/a07_frontend_cache.vvp | findstr /C:"PASS: A-07 frontend/cache joint gate"
	@$(OSS_ENV) "$(ICARUS)" -g2005 -Wall -I rtl -s a07_image_fetch_smoke_tb -o build/a07_image_fetch_smoke.vvp -c $(RTL_FILELIST) tb/models/rv32im_memory_model.v tb/integration/a07_image_fetch_smoke_tb.v
	@$(OSS_ENV) powershell -NoProfile -ExecutionPolicy Bypass -File tools/run_a07_image_smoke.ps1 -Vvp "$(VVP)" -Simulation build/a07_image_fetch_smoke.vvp -Manifest tests/manifest -ImageRoot RISC-V-CPU-Simulator/testcases

b01:
	@$(OSS_ENV) "$(ICARUS)" -g2005 -Wall -I rtl -P rv32_physical_register_file_tb.BE_WIDTH=1 -P rv32_physical_register_file_tb.PHYS_REGS=48 -s rv32_physical_register_file_tb -o build/b01_be1_p48.vvp -c $(RTL_FILELIST) tb/unit/rv32_physical_register_file_tb.v
	@$(OSS_ENV) "$(VVP)" -N build/b01_be1_p48.vvp | findstr /C:"PASS: B-01 PRF BE_WIDTH=1 PHYS_REGS=48"
	@$(OSS_ENV) "$(ICARUS)" -g2005 -Wall -I rtl -P rv32_physical_register_file_tb.BE_WIDTH=2 -P rv32_physical_register_file_tb.PHYS_REGS=64 -s rv32_physical_register_file_tb -o build/b01_be2_p64.vvp -c $(RTL_FILELIST) tb/unit/rv32_physical_register_file_tb.v
	@$(OSS_ENV) "$(VVP)" -N build/b01_be2_p64.vvp | findstr /C:"PASS: B-01 PRF BE_WIDTH=2 PHYS_REGS=64"
	@$(OSS_ENV) "$(ICARUS)" -g2005 -Wall -I rtl -P rv32_physical_register_file_tb.BE_WIDTH=4 -P rv32_physical_register_file_tb.PHYS_REGS=96 -s rv32_physical_register_file_tb -o build/b01_be4_p96.vvp -c $(RTL_FILELIST) tb/unit/rv32_physical_register_file_tb.v
	@$(OSS_ENV) "$(VVP)" -N build/b01_be4_p96.vvp | findstr /C:"PASS: B-01 PRF BE_WIDTH=4 PHYS_REGS=96"

b02:
	@$(OSS_ENV) "$(ICARUS)" -g2005 -Wall -I rtl -P rv32_rename_unit_tb.BE_WIDTH=1 -P rv32_rename_unit_tb.PHYS_REGS=48 -s rv32_rename_unit_tb -o build/b02_be1_p48.vvp -c $(RTL_FILELIST) tb/unit/rv32_rename_unit_tb.v
	@$(OSS_ENV) "$(VVP)" -N build/b02_be1_p48.vvp | findstr /C:"PASS: B-02 rename BE_WIDTH=1 PHYS_REGS=48"
	@$(OSS_ENV) "$(ICARUS)" -g2005 -Wall -I rtl -P rv32_rename_unit_tb.BE_WIDTH=2 -P rv32_rename_unit_tb.PHYS_REGS=64 -s rv32_rename_unit_tb -o build/b02_be2_p64.vvp -c $(RTL_FILELIST) tb/unit/rv32_rename_unit_tb.v
	@$(OSS_ENV) "$(VVP)" -N build/b02_be2_p64.vvp | findstr /C:"PASS: B-02 rename BE_WIDTH=2 PHYS_REGS=64"
	@$(OSS_ENV) "$(ICARUS)" -g2005 -Wall -I rtl -P rv32_rename_unit_tb.BE_WIDTH=4 -P rv32_rename_unit_tb.PHYS_REGS=96 -s rv32_rename_unit_tb -o build/b02_be4_p96.vvp -c $(RTL_FILELIST) tb/unit/rv32_rename_unit_tb.v
	@$(OSS_ENV) "$(VVP)" -N build/b02_be4_p96.vvp | findstr /C:"PASS: B-02 rename BE_WIDTH=4 PHYS_REGS=96"

b03:
	@$(OSS_ENV) "$(ICARUS)" -g2005 -Wall -I rtl -P rv32_rob_tb.BE_WIDTH=1 -P rv32_rob_tb.ROB_ENTRIES=8 -s rv32_rob_tb -o build/b03_be1.vvp -c $(RTL_FILELIST) tb/unit/rv32_rob_tb.v
	@$(OSS_ENV) "$(VVP)" -N build/b03_be1.vvp | findstr /C:"PASS: B-03 ROB BE_WIDTH=1"
	@$(OSS_ENV) "$(ICARUS)" -g2005 -Wall -I rtl -P rv32_rob_tb.BE_WIDTH=2 -P rv32_rob_tb.ROB_ENTRIES=8 -s rv32_rob_tb -o build/b03_be2.vvp -c $(RTL_FILELIST) tb/unit/rv32_rob_tb.v
	@$(OSS_ENV) "$(VVP)" -N build/b03_be2.vvp | findstr /C:"PASS: B-03 ROB BE_WIDTH=2"
	@$(OSS_ENV) "$(ICARUS)" -g2005 -Wall -I rtl -P rv32_rob_tb.BE_WIDTH=4 -P rv32_rob_tb.ROB_ENTRIES=8 -s rv32_rob_tb -o build/b03_be4.vvp -c $(RTL_FILELIST) tb/unit/rv32_rob_tb.v
	@$(OSS_ENV) "$(VVP)" -N build/b03_be4.vvp | findstr /C:"PASS: B-03 ROB BE_WIDTH=4"

b04:
	@$(OSS_ENV) "$(ICARUS)" -g2005 -Wall -I rtl -P rv32_reservation_station_tb.BE_WIDTH=1 -P rv32_reservation_station_tb.ENTRIES=4 -s rv32_reservation_station_tb -o build/b04_be1.vvp -c $(RTL_FILELIST) tb/unit/rv32_reservation_station_tb.v
	@$(OSS_ENV) "$(VVP)" -N build/b04_be1.vvp | findstr /C:"PASS: B-04 RS BE_WIDTH=1 ENTRIES=4"
	@$(OSS_ENV) "$(ICARUS)" -g2005 -Wall -I rtl -P rv32_reservation_station_tb.BE_WIDTH=2 -P rv32_reservation_station_tb.ENTRIES=4 -s rv32_reservation_station_tb -o build/b04_be2.vvp -c $(RTL_FILELIST) tb/unit/rv32_reservation_station_tb.v
	@$(OSS_ENV) "$(VVP)" -N build/b04_be2.vvp | findstr /C:"PASS: B-04 RS BE_WIDTH=2 ENTRIES=4"
	@$(OSS_ENV) "$(ICARUS)" -g2005 -Wall -I rtl -P rv32_reservation_station_tb.BE_WIDTH=4 -P rv32_reservation_station_tb.ENTRIES=4 -s rv32_reservation_station_tb -o build/b04_be4.vvp -c $(RTL_FILELIST) tb/unit/rv32_reservation_station_tb.v
	@$(OSS_ENV) "$(VVP)" -N build/b04_be4.vvp | findstr /C:"PASS: B-04 RS BE_WIDTH=4 ENTRIES=4"

b05:
	@$(OSS_ENV) "$(ICARUS)" -g2005 -Wall -I rtl -s rv32i_alu_tb -o build/b05.vvp -c $(RTL_FILELIST) tb/unit/rv32i_alu_tb.v
	@$(OSS_ENV) "$(VVP)" -N build/b05.vvp | findstr /C:"PASS: B-05 ALU/branch/AGU"
	@$(OSS_ENV) "$(ICARUS)" -g2005 -Wall -I rtl -P rv32i_alu_tb.SHIFT_IMPL=1 -s rv32i_alu_tb -o build/b05_iter_shift.vvp -c $(RTL_FILELIST) tb/unit/rv32i_alu_tb.v
	@$(OSS_ENV) "$(VVP)" -N build/b05_iter_shift.vvp | findstr /C:"PASS: B-05 ALU/branch/AGU"

b06:
	@$(OSS_ENV) "$(ICARUS)" -g2005 -Wall -I rtl -s rv32m_units_tb -o build/b06.vvp -c $(RTL_FILELIST) tb/unit/rv32m_units_tb.v
	@$(OSS_ENV) "$(VVP)" -N build/b06.vvp | findstr /C:"PASS: B-06 multiplier/divider"
	@$(OSS_ENV) "$(ICARUS)" -g2005 -Wall -I rtl -P rv32m_units_tb.MUL_IMPL=1 -s rv32m_units_tb -o build/b06_radix4.vvp -c $(RTL_FILELIST) tb/unit/rv32m_units_tb.v
	@$(OSS_ENV) "$(VVP)" -N build/b06_radix4.vvp | findstr /C:"PASS: B-06 multiplier/divider"
	@$(OSS_ENV) "$(ICARUS)" -g2005 -Wall -I rtl -P rv32m_units_tb.MUL_IMPL=2 -s rv32m_units_tb -o build/b06_unified.vvp -c $(RTL_FILELIST) tb/unit/rv32m_units_tb.v
	@$(OSS_ENV) "$(VVP)" -N build/b06_unified.vvp | findstr /C:"PASS: B-06 multiplier/divider"
	@$(OSS_ENV) "$(ICARUS)" -g2005 -Wall -I rtl -s rv32m_mdu_reservation_station_tb -o build/b06_mdu.vvp -c $(RTL_FILELIST) tb/unit/rv32m_mdu_reservation_station_tb.v
	@$(OSS_ENV) "$(VVP)" -N build/b06_mdu.vvp | findstr /C:"PASS: B-06 MDU RS"
	@$(OSS_ENV) "$(ICARUS)" -g2005 -Wall -I rtl -P rv32m_mdu_reservation_station_tb.MUL_IMPL=1 -s rv32m_mdu_reservation_station_tb -o build/b06_mdu_radix4.vvp -c $(RTL_FILELIST) tb/unit/rv32m_mdu_reservation_station_tb.v
	@$(OSS_ENV) "$(VVP)" -N build/b06_mdu_radix4.vvp | findstr /C:"PASS: B-06 MDU RS"
	@$(OSS_ENV) "$(ICARUS)" -g2005 -Wall -I rtl -P rv32m_mdu_reservation_station_tb.MUL_IMPL=2 -s rv32m_mdu_reservation_station_tb -o build/b06_mdu_unified.vvp -c $(RTL_FILELIST) tb/unit/rv32m_mdu_reservation_station_tb.v
	@$(OSS_ENV) "$(VVP)" -N build/b06_mdu_unified.vvp | findstr /C:"PASS: B-06 MDU RS"

b07:
	@$(OSS_ENV) "$(ICARUS)" -g2005 -Wall -I rtl -P rv32_completion_network_tb.BE_WIDTH=1 -s rv32_completion_network_tb -o build/b07_be1.vvp -c $(RTL_FILELIST) tb/unit/rv32_completion_network_tb.v
	@$(OSS_ENV) "$(VVP)" -N build/b07_be1.vvp | findstr /C:"PASS: B-07 completion network BE_WIDTH=1"
	@$(OSS_ENV) "$(ICARUS)" -g2005 -Wall -I rtl -P rv32_completion_network_tb.BE_WIDTH=2 -s rv32_completion_network_tb -o build/b07_be2.vvp -c $(RTL_FILELIST) tb/unit/rv32_completion_network_tb.v
	@$(OSS_ENV) "$(VVP)" -N build/b07_be2.vvp | findstr /C:"PASS: B-07 completion network BE_WIDTH=2"

b08:
	@$(OSS_ENV) "$(ICARUS)" -g2005 -Wall -I rtl -P rv32_lsq_tb.BE_WIDTH=1 -s rv32_lsq_tb -o build/b08_be1.vvp -c $(RTL_FILELIST) tb/unit/rv32_lsq_tb.v
	@$(OSS_ENV) "$(VVP)" -N build/b08_be1.vvp | findstr /C:"PASS: B-08 LSQ BE_WIDTH=1"
	@$(OSS_ENV) "$(ICARUS)" -g2005 -Wall -I rtl -P rv32_lsq_tb.BE_WIDTH=2 -s rv32_lsq_tb -o build/b08_be2.vvp -c $(RTL_FILELIST) tb/unit/rv32_lsq_tb.v
	@$(OSS_ENV) "$(VVP)" -N build/b08_be2.vvp | findstr /C:"PASS: B-08 LSQ BE_WIDTH=2"

b09:
	@$(OSS_ENV) "$(ICARUS)" -g2005 -Wall -I rtl -P rv32_backend_joint_tb.BE_WIDTH=1 -s rv32_backend_joint_tb -o build/b09_be1.vvp -c $(RTL_FILELIST) tb/unit/rv32_backend_joint_tb.v
	@$(OSS_ENV) "$(VVP)" -N build/b09_be1.vvp | findstr /C:"PASS: B-09 backend joint BE_WIDTH=1"

regression:
	@powershell -NoProfile -Command "python tools/regression.py"

# Area synthesis with Yosys + ASAP7 7.5T RVT TT.
#   make synth CFG=fe1_be1_p64_r32 [FE_WIDTH=1 BE_WIDTH=1 PHYS_REGS=64 ROB_ENTRIES=32]
# synth = explicit register/mux reference (memory_map), synth-bb = blackbox arrays.
# Artifacts go to build/synth/<CFG>[/_bb]/: yosys.log (verbose run log for the
# progress window), synth.log, stat_after_abc.log, cpu_core_synth.v.
asap7-maplib:
	@python tools/filter_asap7_lib.py
	@python tools/liberty2genlib.py

synth: asap7-maplib
	@if not exist "build\synth\$(CFG)" mkdir "build\synth\$(CFG)"
	@$(OSS_ENV) "$(YOSYS)" -p "tcl synth/synth.tcl $(FE_WIDTH) $(BE_WIDTH) $(PHYS_REGS) $(ROB_ENTRIES) build/synth/$(CFG) $(RS_ENTRIES) $(LSQ_ENTRIES) $(ENABLE_CACHE_STATS) $(MUL_IMPL) $(ENABLE_CACHES) $(ENABLE_PREDICTOR) $(FETCH_QUEUE_DEPTH) $(COMPLETION_DEPTH) $(SHIFT_IMPL)" > "build\synth\$(CFG)\yosys.log" 2>&1
	@python tools/audit_synth.py --synth-log "build/synth/$(CFG)/synth.log" --memory-dump "build/synth/$(CFG)/memory_manifest.il" --output "build/synth/$(CFG)/area_audit.json" --profile ff-reference --fe-width $(FE_WIDTH) --be-width $(BE_WIDTH) --phys-regs $(PHYS_REGS) --rob-entries $(ROB_ENTRIES) --rs-entries $(RS_ENTRIES) --lsq-entries $(LSQ_ENTRIES) --cache-stats $(ENABLE_CACHE_STATS) --mul-impl $(MUL_IMPL) --shift-impl $(SHIFT_IMPL) --caches $(ENABLE_CACHES) --predictor $(ENABLE_PREDICTOR) --fetch-queue-depth $(FETCH_QUEUE_DEPTH) --completion-depth $(COMPLETION_DEPTH)

synth-bb: asap7-maplib
	@if not exist "build\synth\$(CFG)_bb" mkdir "build\synth\$(CFG)_bb"
	@$(OSS_ENV) "$(YOSYS)" -p "tcl synth/synth_bb.tcl $(FE_WIDTH) $(BE_WIDTH) $(PHYS_REGS) $(ROB_ENTRIES) build/synth/$(CFG)_bb $(RS_ENTRIES) $(LSQ_ENTRIES) $(ENABLE_CACHE_STATS) $(MUL_IMPL) $(ENABLE_CACHES) $(ENABLE_PREDICTOR) $(FETCH_QUEUE_DEPTH) $(COMPLETION_DEPTH) $(SHIFT_IMPL)" > "build\synth\$(CFG)_bb\yosys.log" 2>&1
	@python tools/audit_synth.py --synth-log "build/synth/$(CFG)_bb/synth.log" --memory-dump "build/synth/$(CFG)_bb/memory_manifest.il" --output "build/synth/$(CFG)_bb/area_audit.json" --profile logic-blackbox --fe-width $(FE_WIDTH) --be-width $(BE_WIDTH) --phys-regs $(PHYS_REGS) --rob-entries $(ROB_ENTRIES) --rs-entries $(RS_ENTRIES) --lsq-entries $(LSQ_ENTRIES) --cache-stats $(ENABLE_CACHE_STATS) --mul-impl $(MUL_IMPL) --shift-impl $(SHIFT_IMPL) --caches $(ENABLE_CACHES) --predictor $(ENABLE_PREDICTOR) --fetch-queue-depth $(FETCH_QUEUE_DEPTH) --completion-depth $(COMPLETION_DEPTH)
