# Прошивка софт-процессора (PicoRV32, RV32IMC)

```
include/hw.h       карта памяти и регистры периферии (fpga/rtl/synth_core.sv)
include/lib.h      общий рантайм: UART, printf-подмножество, CRC-32, SPI-флеш, string.h
lib/               его реализация (без libc, -nostdlib; libgcc — для 64-битной арифметики)
boot/              загрузчик в ROM (0x0010_0000, ≤ 4 КБ, без .data/.bss)
fw/                прошивка в RAM с адреса 0: start.S, link.ld, main.c
test/              хост-тесты на обычном gcc (+ ASan/UBSan): unity_lite.h, test_*.c
tools/bin2hex.py   BIN → HEX 32-битных слов (инициализация RAM в симуляции)
tools/bin2rom.py   BIN → SV case-ROM (fpga/rtl/soc/boot_rom.sv)
tools/load.py      загрузка прошивки по UART с компьютера (pyserial)
```

Сборка из корня репозитория:

| Команда | Результат |
|---|---|
| `make fw` | `build/sw/fw.{elf,bin,hex,map}`, `build/sw/boot.{elf,bin}` |
| `make swtest` | хост-тесты `sw/test` |
| `make bootrom` | пересобрать загрузчик и `fpga/rtl/soc/boot_rom.sv` (CI проверяет, что файл актуален) |

Тулчейн: `riscv-none-elf-` (xPack) или `riscv64-unknown-elf-` (Ubuntu: `apt install gcc-riscv64-unknown-elf`),
выбирается автоматически; явно — `make fw CROSS=riscv-none-elf-`.

## Загрузка прошивки

Загрузчик (`boot/boot.c`) после сброса печатает `AVK6 boot`, ждёт образ по UART `SYSINFO_BOOT_WAIT` мс
(500 по умолчанию), затем грузит образ из SPI-флеша, а если его нет — ждёт образ по UART бесконечно.
Работающая прошивка тоже реагирует на магическое слово `AVKB` и передаёт управление загрузчику,
поэтому новая прошивка заливается без нажатия сброса и без пересборки битстрима:

```bash
make fw
python3 sw/tools/load.py /dev/ttyUSB1 build/sw/fw.bin           # в RAM, запуск
python3 sw/tools/load.py /dev/ttyUSB1 build/sw/fw.bin --flash   # и сохранить во флеш
```

Протокол: `AVKB` → устройство отвечает `LOAD` → `len:u32le flags:u32le образ crc32:u32le`
(`flags` бит 0 — записать во флеш) → `OK` и запуск, либо `E1` (длина), `E2` (CRC), `E3` (проверка флеша).
Во флеше по адресу `SYSINFO_FW_FLASH`: заголовок `{"AVKF", len, crc}`, образ — со смещения +256.
Смещение — параметр `FW_FLASH_OFFSET` ядра (9K: 1 МБ, 20K: 5 МБ — за битстримом; уточнить на железе).

Системные тесты `fpga/sim/system/test_synth_core_soc.py` прогоняют всё это в Verilator: загрузку по UART,
отказ по CRC и повтор, запись во флеш (модель SPI NOR) и загрузку из него, повторный вход из прошивки,
печать MIDI-событий прошивкой.
