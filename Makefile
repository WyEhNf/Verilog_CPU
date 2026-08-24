SHELL := cmd.exe
.SHELLFLAGS := /C

.PHONY: doctor lint unit matrix h01 h02 h03 h04 b01 regression

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
RTL_FILELIST = rtl/filelist.f

doctor:
	@$(OSS_ENV) "$(ICARUS)" -V
	@$(OSS_ENV) "$(VERILATOR)" --version
	@$(OSS_ENV) "$(YOSYS)" --version
	@$(OSS_ENV) "$(GTKWAVE)" --version
	@"$(RISCV_PREFIX)gcc.exe" --version
	@"$(RISCV_PREFIX)objdump.exe" --version
	@"$(RISCV_PREFIX)objcopy.exe" --version
	@powershell -NoProfile -Command "& '$(RISCV_PREFIX)gcc.exe' -print-multi-lib | Select-String 'rv32i/ilp32|rv32im/ilp32'"

lint:
	@$(OSS_ENV) "$(ICARUS)" -g2005 -Wall -I rtl -s cpu_core -o build/h00_lint.vvp -c $(RTL_FILELIST)
	@$(OSS_ENV) "$(ICARUS)" -g2005 -Wall -I rtl -s rv32im_defs_tb -o build/h01_defs_lint.vvp -c $(RTL_FILELIST) tb/unit/rv32im_defs_tb.v
	@$(OSS_ENV) "$(ICARUS)" -g2005 -Wall -I rtl -s h01_channel_tb -o build/h01_channel_lint.vvp -c $(RTL_FILELIST) tb/integration/h01_channel_tb.v
	@$(OSS_ENV) "$(VERILATOR)" --lint-only --language 1364-2005 -Wall -Irtl rtl/cpu_core.v
	@$(OSS_ENV) "$(VERILATOR)" --lint-only --language 1364-2005 -Wall -Irtl rtl/common/rv32im_tag_compare.v
	@$(OSS_ENV) "$(VERILATOR)" --lint-only --language 1364-2005 -Wall -Irtl rtl/common/rv32im_fifo.v
	@$(OSS_ENV) "$(VERILATOR)" --lint-only --language 1364-2005 -Wall -Irtl rtl/common/rv32im_skid_buffer.v
	@$(OSS_ENV) "$(VERILATOR)" --lint-only --language 1364-2005 -Wall -Irtl rtl/common/rv32im_prefix_alloc.v
	@$(OSS_ENV) "$(VERILATOR)" --lint-only --language 1364-2005 -Wall -Irtl rtl/common/rv32im_priority_select.v
	@$(OSS_ENV) "$(YOSYS)" -q -p "read_verilog -I rtl rtl/cpu_core.v; hierarchy -check -top cpu_core; proc; check"
	@$(OSS_ENV) "$(YOSYS)" -q -p "read_verilog -I rtl rtl/common/rv32im_tag_compare.v; hierarchy -check -top rv32im_tag_compare; proc; check"
	@$(OSS_ENV) "$(YOSYS)" -q -p "read_verilog -I rtl rtl/common/rv32im_fifo.v; hierarchy -check -top rv32im_fifo; proc; memory; check"
	@$(OSS_ENV) "$(YOSYS)" -q -p "read_verilog -I rtl rtl/common/rv32im_skid_buffer.v; hierarchy -check -top rv32im_skid_buffer; proc; check"
	@$(OSS_ENV) "$(YOSYS)" -q -p "read_verilog -I rtl rtl/common/rv32im_prefix_alloc.v; hierarchy -check -top rv32im_prefix_alloc; proc; check"
	@$(OSS_ENV) "$(YOSYS)" -q -p "read_verilog -I rtl rtl/common/rv32im_priority_select.v; hierarchy -check -top rv32im_priority_select; proc; check"

unit:
	@if not "$(NAME)"=="h00" if not "$(NAME)"=="" (echo Unknown unit NAME=$(NAME) & exit /b 2)
	@$(OSS_ENV) "$(ICARUS)" -g2005 -Wall -I rtl -s cpu_core_h00_tb -o build/cpu_core_h00_tb.vvp -c $(RTL_FILELIST) tb/unit/cpu_core_h00_tb.v
	@$(OSS_ENV) "$(VVP)" -N build/cpu_core_h00_tb.vvp
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

b01:
	@$(OSS_ENV) "$(ICARUS)" -g2005 -Wall -I rtl -P rv32_physical_register_file_tb.BE_WIDTH=1 -P rv32_physical_register_file_tb.PHYS_REGS=48 -s rv32_physical_register_file_tb -o build/b01_be1_p48.vvp -c $(RTL_FILELIST) tb/unit/rv32_physical_register_file_tb.v
	@$(OSS_ENV) "$(VVP)" -N build/b01_be1_p48.vvp
	@$(OSS_ENV) "$(ICARUS)" -g2005 -Wall -I rtl -P rv32_physical_register_file_tb.BE_WIDTH=2 -P rv32_physical_register_file_tb.PHYS_REGS=64 -s rv32_physical_register_file_tb -o build/b01_be2_p64.vvp -c $(RTL_FILELIST) tb/unit/rv32_physical_register_file_tb.v
	@$(OSS_ENV) "$(VVP)" -N build/b01_be2_p64.vvp
	@$(OSS_ENV) "$(ICARUS)" -g2005 -Wall -I rtl -P rv32_physical_register_file_tb.BE_WIDTH=4 -P rv32_physical_register_file_tb.PHYS_REGS=96 -s rv32_physical_register_file_tb -o build/b01_be4_p96.vvp -c $(RTL_FILELIST) tb/unit/rv32_physical_register_file_tb.v
	@$(OSS_ENV) "$(VVP)" -N build/b01_be4_p96.vvp

regression:
	@powershell -NoProfile -Command "python tools/regression.py"
