# RISC-V software for PicoRV32 (RV32IMC): boot ROM and firmware; host unit tests.
# Toolchain: riscv-none-elf- (xPack) or riscv64-unknown-elf- (Ubuntu gcc-riscv64-unknown-elf).
#
#   make           firmware + boot loader -> $(BUILD)/fw.{elf,bin,hex,map}, boot.{elf,bin}
#   make bootrom   regenerate fpga/rtl/soc/boot_rom.sv from the boot loader
#   make test      host unit tests (sw/test, native gcc)

CROSS ?= $(firstword $(foreach p,riscv-none-elf- riscv64-unknown-elf- riscv32-unknown-elf-,\
           $(if $(shell command -v $(p)gcc 2>/dev/null),$(p))))

CC      := $(CROSS)gcc
OBJCOPY := $(CROSS)objcopy
SIZE    := $(CROSS)size
PYTHON  ?= python3
HOSTCC  ?= gcc

BUILD   ?= build
RAM_WORDS := 8192
BOOTROM_SV := ../fpga/rtl/soc/boot_rom.sv

ARCH    := -march=rv32imc -mabi=ilp32
CFLAGS  := $(ARCH) -Os -g -std=c11 -ffreestanding -fno-builtin -ffunction-sections -fdata-sections \
           -fno-delete-null-pointer-checks -fno-tree-loop-distribute-patterns \
           -Wall -Wextra -Werror -Iinclude -Ifw
LDFLAGS := $(ARCH) -nostdlib -nostartfiles -Wl,--gc-sections -Wl,--no-warn-rwx-segments

LIB_SRCS  := lib/uart.c lib/xprintf.c lib/crc32.c lib/string.c lib/flash.c lib/log.c
FW_SRCS   := fw/start.S fw/main.c fw/hw.c fw/synth.c fw/params.c fw/patch.c fw/console.c fw/voice_alloc.c fw/avk.c \
             fw/ui.c fw/lcd.c fw/font.c fw/font8x16.c $(LIB_SRCS)
BOOT_SRCS := boot/start.S boot/boot.c $(filter-out lib/log.c,$(LIB_SRCS))

obj = $(patsubst %,$(BUILD)/obj/%.o,$(1))
FW_OBJS   := $(call obj,$(FW_SRCS))
BOOT_OBJS := $(call obj,$(BOOT_SRCS))
HEADERS   := $(wildcard include/*.h fw/*.h)

.PHONY: all bootrom test clean
all: $(BUILD)/fw.elf $(BUILD)/fw.bin $(BUILD)/fw.hex $(BUILD)/boot.bin
	$(SIZE) $(BUILD)/fw.elf $(BUILD)/boot.elf

ifeq ($(CROSS),)
$(BUILD)/%.o:
	$(error no RISC-V gcc found: install gcc-riscv64-unknown-elf or xPack riscv-none-elf-gcc, or set CROSS=)
endif

$(BUILD)/obj/%.c.o: %.c $(HEADERS)
	@mkdir -p $(dir $@)
	$(CC) $(CFLAGS) -c $< -o $@

$(BUILD)/obj/%.S.o: %.S
	@mkdir -p $(dir $@)
	$(CC) $(ARCH) -c $< -o $@

$(BUILD)/fw.elf: $(FW_OBJS) fw/link.ld
	$(CC) $(LDFLAGS) -Wl,-T,fw/link.ld -Wl,-Map,$(BUILD)/fw.map $(FW_OBJS) -lgcc -o $@

$(BUILD)/boot.elf: $(BOOT_OBJS) boot/link.ld
	$(CC) $(LDFLAGS) -Wl,-T,boot/link.ld -Wl,-Map,$(BUILD)/boot.map $(BOOT_OBJS) -lgcc -o $@

$(BUILD)/%.bin: $(BUILD)/%.elf
	$(OBJCOPY) -O binary $< $@

$(BUILD)/fw.hex: $(BUILD)/fw.bin tools/bin2hex.py
	$(PYTHON) tools/bin2hex.py $< $@ --words $(RAM_WORDS)

bootrom: $(BUILD)/boot.bin
	$(PYTHON) tools/bin2rom.py $< $(BOOTROM_SV)

# ------------------------------------------------------------ host unit tests
TEST_SRCS := $(wildcard test/test_*.c)
TEST_BINS := $(patsubst test/%.c,$(BUILD)/host/%,$(TEST_SRCS))

test: $(TEST_BINS)
	@set -e; for t in $(TEST_BINS); do echo "== $$t"; $$t; done

$(BUILD)/host/test_%: test/test_%.c test/unity_lite.h $(HEADERS) $(wildcard lib/*.c fw/*.c)
	@mkdir -p $(dir $@)
	$(HOSTCC) -std=c11 -O1 -g -Wall -Wextra -Werror -fsanitize=address,undefined -DHOST_TEST \
		-Iinclude -Ifw -Itest $< -o $@ -lm

clean:
	rm -rf $(BUILD)
