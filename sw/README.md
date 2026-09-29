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

## Консоль (UART, 115200 или `UART_BAUD` ядра)

| Команда | Что делает |
|---|---|
| `list`, `get <p>`, `set <p> <v>` | параметры из таблицы `fw/patch.c` (те же, что в меню) |
| `route <k> <src> <via> <dst> <depth>` | маршрут матрицы модуляции 1…7 (0 — вибрато); номера — `SRC_*`, `DST_*` в `hw.h` |
| `note <n> [vel]`, `off <n>` | нажать / отпустить ноту |
| `screen`, `panel` | текст экрана; энкодеры, кнопки, ручки |
| `avk` | коды и значения ВХ1/ВХ2, частота и счётчик фронтов СИНХР, текущие значения шины сигналов |
| `cal <1\|2> zero` | калибровка нуля входа: на вход подан 0 В |
| `cal <1\|2> <мВ>` | калибровка масштаба (после `zero`): на вход подано известное напряжение |

Параметры связи с АВК: `in1mix`, `in2mix` (входы в ВЫХ), `out2src`, `out2gain` (источник и уровень ВЫХ2),
`syncmode` (`off` / `lfo` — фронт СИНХР сбрасывает фазу LFO / `note` — фронт перезапускает ноту `syncnote`),
`slot1op`…`slot2k` (операция слота MATH, источники A и B, коэффициент k), `fxmix` (уровень слотов в ВЫХ).

Задержки (слоты DELAY): `dly1src`, `dly1time` (мс), `dly1fb` (повтор, %), `dly1lvl` (уровень в ВЫХ), то же `dly2*`;
`dlysync on` — время задержки равно периоду СИНХР. `mem <слово> [значение]` — чтение/запись внешней памяти
(проверка SDRAM на плате).

Хорус/флэнжер: `chosrc`, `chobase`, `chodepth` (0.1 мс), `chorate`, `chofb`, `cholvl`. Реверберация: `revsrc`,
`revroom`, `revdamp`, `revlvl`. `hsync` — жёсткая синхронизация генераторов от СИНХР (`osc1`/`osc2`/`both`);
детектор огибающей: `follsrc`, `follatk`, `follrel`, источник 10 в `route`; `out2src pitch` — на ВЫХ2
напряжение высоты последней ноты (1 В/окт, 0 В = нота 60).
