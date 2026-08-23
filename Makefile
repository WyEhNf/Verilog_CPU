SHELL := cmd.exe
.SHELLFLAGS := /C

.PHONY: doctor lint unit matrix

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
	@$(OSS_ENV) "$(VERILATOR)" --lint-only --language 1364-2005 -Wall -Irtl rtl/cpu_core.v
	@$(OSS_ENV) "$(YOSYS)" -q -p "read_verilog -I rtl rtl/cpu_core.v; hierarchy -check -top cpu_core; proc; check"

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
