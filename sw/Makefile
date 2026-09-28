# RISC-V firmware for PicoRV32 (RV32IMC). Toolchain: riscv-none-elf- (xPack) or
# riscv64-unknown-elf- (Ubuntu gcc-riscv64-unknown-elf), whichever is found first.

CROSS ?= $(firstword $(foreach p,riscv-none-elf- riscv64-unknown-elf- riscv32-unknown-elf-,\
           $(if $(shell command -v $(p)gcc 2>/dev/null),$(p))))
ifeq ($(CROSS),)
$(error no RISC-V gcc found: install gcc-riscv64-unknown-elf or xPack riscv-none-elf-gcc, or set CROSS=)
endif

CC      := $(CROSS)gcc
OBJCOPY := $(CROSS)objcopy
SIZE    := $(CROSS)size
PYTHON  ?= python3

BUILD   ?= build
TARGET  := $(BUILD)/fw
RAM_WORDS := 8192

ARCH    := -march=rv32imc -mabi=ilp32
CFLAGS  := $(ARCH) -Os -g -std=c11 -ffreestanding -fno-builtin -ffunction-sections -fdata-sections \
           -Wall -Wextra -Werror -Iinclude
LDFLAGS := $(ARCH) -nostdlib -nostartfiles -Wl,--gc-sections -Wl,--no-warn-rwx-segments -Wl,-T,link.ld -Wl,-Map,$(TARGET).map

SRCS := src/start.S src/main.c
OBJS := $(patsubst src/%,$(BUILD)/%.o,$(SRCS))

.PHONY: all clean
all: $(TARGET).elf $(TARGET).bin $(TARGET).hex
	$(SIZE) $(TARGET).elf

$(BUILD)/%.c.o: src/%.c include/hw.h | $(BUILD)
	$(CC) $(CFLAGS) -c $< -o $@

$(BUILD)/%.S.o: src/%.S | $(BUILD)
	$(CC) $(ARCH) -c $< -o $@

$(TARGET).elf: $(OBJS) link.ld
	$(CC) $(LDFLAGS) $(OBJS) -o $@

$(TARGET).bin: $(TARGET).elf
	$(OBJCOPY) -O binary $< $@

$(TARGET).hex: $(TARGET).bin tools/bin2hex.py
	$(PYTHON) tools/bin2hex.py $< $@ --words $(RAM_WORDS)

$(BUILD):
	mkdir -p $@

clean:
	rm -rf $(BUILD)
