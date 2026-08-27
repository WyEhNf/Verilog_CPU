SHELL := cmd.exe
.SHELLFLAGS := /C

.PHONY: doctor lint unit matrix h01 h02 h03 h04 a01 a02 a03 a04 a05 a06 b01 b02 b03 b04 b05 b06 b07 b08 b09 regression

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
	@$(OSS_ENV) "$(VERILATOR)" --lint-only --language 1364-2005 -Wall -Irtl rtl/memory/rv32_memory_bridge.v
	@$(OSS_ENV) "$(YOSYS)" -q -p "read_verilog -I rtl rtl/memory/rv32_memory_bridge.v; hierarchy -check -top rv32_memory_bridge; proc; check"

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

b06:
	@$(OSS_ENV) "$(ICARUS)" -g2005 -Wall -I rtl -s rv32m_units_tb -o build/b06.vvp -c $(RTL_FILELIST) tb/unit/rv32m_units_tb.v
	@$(OSS_ENV) "$(VVP)" -N build/b06.vvp | findstr /C:"PASS: B-06 multiplier/divider"
	@$(OSS_ENV) "$(ICARUS)" -g2005 -Wall -I rtl -s rv32m_mdu_reservation_station_tb -o build/b06_mdu.vvp -c $(RTL_FILELIST) tb/unit/rv32m_mdu_reservation_station_tb.v
	@$(OSS_ENV) "$(VVP)" -N build/b06_mdu.vvp | findstr /C:"PASS: B-06 MDU RS"

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
