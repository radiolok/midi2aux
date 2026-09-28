# FPGA synth for AVK-6: lint, simulation, model tests, RISC-V firmware.
# MIDI2AUX (fw/) is built with PlatformIO, not here.
#
#   make lint    verilator --lint-only -Wall (every core + board tops with vendor stubs)
#   make unit    RTL unit tests: cocotb + Verilator, compared with the Python models
#   make sim     system tests: MIDI stimulus -> core -> I2S -> WAV -> Python checks
#   make model   pytest of the Python models + reference WAVs
#   make fw      RISC-V firmware (sw/) -> ELF/BIN/HEX
#   make test    lint + model + unit + sim
#   make luts    regenerate RTL tables from the Python model
#   make plots   refresh the plots committed for fpga/sim/README.md and fpga/model/README.md
#   make bitstream-9k / bitstream-20k   Gowin EDA (gw_sh), local only

PYTHON    ?= python3
VERILATOR ?= verilator
GW_SH     ?= gw_sh
BUILD     ?= build

RTL_DIR   := fpga/rtl
RTL_FILES := $(addprefix $(RTL_DIR)/,$(shell grep -v '^\s*\#' $(RTL_DIR)/files.f))
BOARDS    := tang_nano_9k tang_nano_20k
CORES     := stub_core mono_core
GOWIN_STUBS := fpga/sim/gowin_stubs/rPLL.v
PYTEST    ?= $(PYTHON) -m pytest -q

.PHONY: all test lint unit sim model refs fw luts plots clean bitstream-9k bitstream-20k

all: test fw

test: lint model unit sim

# ------------------------------------------------------------------ RTL lint
lint:
	$(foreach c,$(CORES),$(VERILATOR) --lint-only -Wall --top-module $(c) $(RTL_FILES) &&) true
	$(foreach b,$(BOARDS),$(VERILATOR) --lint-only -Wall --top-module top \
		$(GOWIN_STUBS) $(RTL_FILES) fpga/boards/$(b)/pll_sys.v fpga/boards/$(b)/top.sv &&) true

# ---------------------------------------------------------------- simulation
unit:
	$(PYTEST) fpga/sim/unit

sim:
	$(PYTEST) fpga/sim/system

# -------------------------------------------------------------- Python models
model: refs
	$(PYTEST) fpga/model

refs:
	cd fpga/model && $(PYTHON) gen_refs.py --out $(abspath $(BUILD)/model)

luts:
	cd fpga/model && $(PYTHON) -m synthmodel.luts

plots: sim refs
	cp $(BUILD)/sim/stub_core/stub_core.png $(BUILD)/sim/mono_core/mono_core.png fpga/sim/img/
	cp $(BUILD)/model/models.png fpga/model/img/

# ------------------------------------------------------------ RISC-V firmware
fw:
	$(MAKE) -C sw BUILD=$(abspath $(BUILD)/sw)

# ------------------------------------------------------ Gowin EDA (local only)
bitstream-9k bitstream-20k: bitstream-%:
	mkdir -p $(BUILD)/gowin/$*
	cd $(BUILD)/gowin/$* && $(GW_SH) $(abspath fpga/boards/tang_nano_$*/build.tcl)

clean:
	rm -rf $(BUILD)
