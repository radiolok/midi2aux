# FPGA synth for AVK-6: lint, simulation, model tests, RISC-V firmware.
# MIDI2AUX (fw/) is built with PlatformIO, not here.
#
#   make lint    verilator --lint-only -Wall (portable RTL + board tops with vendor stubs)
#   make sim     Verilator TB: MIDI stimulus -> stub_core -> I2S -> WAV, then Python checks
#   make model   pytest of the Python models + reference WAVs
#   make fw      RISC-V firmware (sw/) -> ELF/BIN/HEX
#   make test    lint + model + sim
#   make luts    regenerate RTL tables from the Python model
#   make plots   refresh the plots committed for fpga/sim/README.md and fpga/model/README.md
#   make bitstream-9k / bitstream-20k   Gowin EDA (gw_sh), local only

SYS_CLK_HZ   ?= 99000000
FS_HZ        ?= 48000
DATA_W       ?= 18
TONE_HZ      ?= 440
SIM_DURATION ?= 0.3

PYTHON    ?= python3
VERILATOR ?= verilator
GW_SH     ?= gw_sh
BUILD     ?= build

RTL_DIR   := fpga/rtl
RTL_FILES := $(addprefix $(RTL_DIR)/,$(shell grep -v '^\s*\#' $(RTL_DIR)/files.f))
BOARDS    := tang_nano_9k tang_nano_20k
GOWIN_STUBS := fpga/sim/gowin_stubs/rPLL.v

SIM_DIR   := $(BUILD)/sim
SIM_BIN   := $(SIM_DIR)/obj/Vstub_core
SIM_PARAMS := -GSYS_CLK_HZ=$(SYS_CLK_HZ) -GFS_HZ=$(FS_HZ) -GDATA_W=$(DATA_W) -GTONE_HZ=$(TONE_HZ)
MIDI_STIM := fpga/sim/stimuli/stub_midi.txt

.PHONY: all test lint sim model refs fw luts plots clean bitstream-9k bitstream-20k

all: test fw

test: lint model sim

# ------------------------------------------------------------------ RTL lint
lint:
	$(VERILATOR) --lint-only -Wall --top-module stub_core $(RTL_FILES)
	$(foreach b,$(BOARDS),$(VERILATOR) --lint-only -Wall --top-module top \
		$(GOWIN_STUBS) $(RTL_FILES) fpga/boards/$(b)/pll_sys.v fpga/boards/$(b)/top.sv &&) true

# ---------------------------------------------------------------- simulation
$(SIM_BIN): $(RTL_FILES) fpga/sim/tb_stub_core.cpp Makefile
	mkdir -p $(SIM_DIR)/obj
	$(VERILATOR) --cc --exe --build -j 0 -Wall -O3 --top-module stub_core $(SIM_PARAMS) \
		-CFLAGS "-O2 -DSYS_CLK_HZ=$(SYS_CLK_HZ) -DDATA_W=$(DATA_W)" \
		-Mdir $(SIM_DIR)/obj $(RTL_FILES) $(abspath fpga/sim/tb_stub_core.cpp)

sim: $(SIM_BIN)
	$(SIM_BIN) --duration $(SIM_DURATION) --midi $(MIDI_STIM) \
		--wav $(SIM_DIR)/stub_core.wav --json $(SIM_DIR)/stub_core_tb.json
	$(PYTHON) fpga/sim/check_stub.py --wav $(SIM_DIR)/stub_core.wav --json $(SIM_DIR)/stub_core_tb.json \
		--out $(SIM_DIR) --sys-clk $(SYS_CLK_HZ) --fs $(FS_HZ) --tone $(TONE_HZ) --data-w $(DATA_W)

# -------------------------------------------------------------- Python models
model: refs
	cd fpga/model && $(PYTHON) -m pytest -q

refs:
	cd fpga/model && $(PYTHON) gen_refs.py --out $(abspath $(BUILD)/model)

luts:
	cd fpga/model && $(PYTHON) -m synthmodel.luts --data-w $(DATA_W)

plots: sim refs
	cp $(SIM_DIR)/stub_core.png fpga/sim/img/
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
