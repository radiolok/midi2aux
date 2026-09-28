# FPGA-синтезатор для АВК-6 — RTL, симуляция, модели

ТЗ и план: [`.plans/fpga-synth/`](../.plans/fpga-synth/). Сейчас реализован **этап 0** (инфраструктура):
заглушечное ядро `stub_core` — синус 440 Гц в левый канал и пила в правый через I2S, эхо байтов MIDI
для тестбенча, «мигалка».

Графики и результаты: симуляция — [`sim/README.md`](sim/README.md), модели — [`model/README.md`](model/README.md).

## Структура

```
fpga/
  rtl/                 переносимый RTL (без примитивов производителя)
    files.f            список файлов — общий для Verilator и Gowin EDA
    stub_core.sv       ядро этапа 0
    audio/             audio_clkgen (BCK/LRCK/audio_tick), i2s_tx, nco_sine,
                       sine_quarter_rom.sv (генерируется: make luts)
    midi/              uart_rx, uart_tx, midi_parser
    common/            sync_fifo
    soc/               шина PicoRV32: RAM, boot ROM (генерируется: make bootrom), периферия, SPI
    third_party/       PicoRV32 (ISC), без изменений
    mono_core.sv       ядро этапа 1 (один голос, без процессора)
    synth_core.sv      ядро с этапа 2 (PicoRV32 + звуковой тракт)
    lint.vlt           исключения линта (third_party, board-top)
  boards/
    tang_nano_9k/      top_synth.sv / top_mono.sv, pll_sys.v (rPLL), .cst на каждое ядро, .sdc, build.tcl
    tang_nano_20k/     то же для 20K
  sim/
    tb/tb_audio.cpp    общий тестбенч Verilator для ядер: MIDI → ядро → декодер I2S → WAV + JSON
    system/            системные тесты (pytest): сборка, прогон, анализ WAV, графики
    unit/              юнит-тесты блоков RTL (cocotb + Verilator), сравнение с моделями
    stimuli/           файлы стимулов MIDI
    gowin_stubs/       заглушки примитивов Gowin для линта board-top
  model/
    synthmodel/        Python-модели: clocks, nco, adsr, svf, analysis, wavio, luts
    tests/             pytest
    gen_refs.py        эталонные WAV + графики моделей
  requirements.txt
```

## Установка (Ubuntu 24.04)

```bash
sudo apt-get install verilator gcc-riscv64-unknown-elf make g++   # Verilator 5.020, GCC 13
pip install -r fpga/requirements.txt                               # numpy, scipy, matplotlib, pytest
```

Другие дистрибутивы: Verilator ≥ 5.0 (из пакетов или из исходников), любой RISC-V GCC —
`riscv64-unknown-elf-gcc` или xPack `riscv-none-elf-gcc`; префикс определяется автоматически,
можно задать явно: `make fw CROSS=riscv-none-elf-`.

## Команды (из корня репозитория)

| Команда | Что делает |
|---|---|
| `make lint` | `verilator --lint-only -Wall`: ядро и оба board-top (с заглушкой `rPLL`) |
| `make unit` | юнит-тесты блоков RTL (cocotb) |
| `make sim` | системные тесты: ядро целиком, MIDI → WAV → проверки |
| `make model` | pytest моделей + эталонные WAV в `build/model/` |
| `make fw` | прошивка RISC-V → `build/sw/fw.{elf,bin,hex,map}` |
| `make test` | `lint` + `model` + `unit` + `sim` — то же, что проверяет CI (кроме `fw`) |
| `make all` | `test` + `fw` |
| `make luts` | перегенерировать `rtl/audio/sine_quarter_rom.sv` из модели |
| `make plots` | `sim` + `refs` и обновить графики в `sim/img/`, `model/img/` |
| `make bitstream-9k`, `make bitstream-20k` | Gowin EDA, только локально |

Отдельный тест: `python3 -m pytest -q fpga/sim/system/test_mono_core.py`.

Результаты в `build/sim/<тест>/`: WAV (стерео, 24 бит — можно послушать), PNG (осциллограммы, спектры),
JSON (сводка тестбенча). В CI — артефакты `sim-results`, `model-refs`, `firmware` на странице запуска workflow.

## Что проверяется

Тестбенч (`tb/tb_audio.cpp`, код возврата ≠ 0 при ошибке):
- формат I2S на уровне выводов, как его принимает ЦАП: LRCK/DIN меняются только по спаду BCK,
  32 такта BCK на слот, MSB через такт после фронта LRCK, биты ниже `DATA_W` — нули, период BCK постоянный;
- MIDI: байты из файла стимулов передаются на `midi_rx` с таймингом 31250 бод; принятые ядром байты
  совпадают с отправленными (ядра с `-DMIDI_ECHO`).

`system/test_stub_core.py` (этап 0):
- fs = sys_clk / (128 · BCK_HALF), отклонение от 48 кГц ≤ 3 %;
- L (синус): основной тон 440 Гц ± 0.5 %, THD ≤ −70 дБ, THD+N ≤ −60 дБ, пик 0.99…1.0 FS;
- R (пила): основной тон ± 0.5 %, H2/H1 = −6 ± 1 дБ;
- оба канала **побитово** совпадают с моделью `synthmodel.nco`.

`system/test_mono_core.py` (этап 1): частота каждой ноты ± 0.1 % (running status, Note On vel 0,
байт realtime внутри сообщения, omni, pitch bend ±2 полутона), гейт на R, тишина после Note Off,
All Notes Off и Stop, задержка MIDI → звук ≤ 3 мс.

Юнит-тесты (`unit/`): `uart_rx` (рассогласование скорости ±3 %, ошибка стопа, помеха), `sync_fifo`,
`midi_parser` (случайные потоки против `synthmodel.midi`), `pitch2inc` (побитово с `synthmodel.pitch`,
точность < 0.02 цента), `dac_scale`.

### Формат стимулов MIDI

Текст, строка — `<время_мс> <байт hex> [<байт hex> …]`, `#` — комментарий. Байты строки идут
подряд с указанного времени (или сразу после предыдущего сообщения, если оно ещё передаётся).
Пример — `sim/stimuli/stub_midi.txt`; тесты генерируют стимулы сами (`vsys.write_midi`). Входы ВХ1/ВХ2 из файлов подключатся к тестбенчу вместе
с моделью АЦП (этап 6), сейчас у ядра этих входов нет.

## Тактирование

Кварц 27 МГц → rPLL → sys_clk **99 МГц** (27 · 11 / 3, VCO 792 МГц).
BCK = sys_clk / (2 · 16) = 3.094 МГц = 64 · fs, **fs = 48 339.84 Гц** (+0.7 % от 48 кГц).
Инкремент фазы NCO считается от фактической fs (`synthmodel.clocks`, `stub_core.sv`).
Для другой sys_clk достаточно поменять `SYS_CLK_HZ` — делитель BCK выбирается автоматически
(нужно sys_clk ≥ 256 · fs).

## Gowin EDA (битстрим, локально)

В CI Gowin EDA нет. Нужна Gowin EDA (Education достаточно) с `gw_sh` в `PATH`:

```bash
make bitstream-9k             # synth_core → build/gowin/9k-synth/impl/pnr/avk_synth_9k.fs
make bitstream-9k CORE=mono   # mono_core (этап 1, без процессора)
make bitstream-20k            # → build/gowin/20k-synth/impl/pnr/avk_synth_20k.fs
openFPGALoader -b tangnano9k build/gowin/9k-synth/impl/pnr/avk_synth_9k.fs       # в SRAM
openFPGALoader -b tangnano20k -f build/gowin/20k-synth/impl/pnr/avk_synth_20k.fs # во флеш
```

После прошивки битстрима `synth_core` загрузить прошивку: `python3 sw/tools/load.py <порт> build/sw/fw.bin`
(см. [`sw/README.md`](../sw/README.md)).

Или в GUI: новый проект под нужный кристалл (9K: `GW1NR-LV9QN88PC6/I5`, 20K: `GW2AR-LV18QN88C8/I7`),
добавить файлы из `rtl/files.f`, `boards/<плата>/pll_sys.v`, `top_<ядро>.sv`, `<плата>_<ядро>.cst`, `.sdc`; top module — `top`,
Verilog Language — SystemVerilog 2017.

`build.tcl` проверен только «всухую» (на заглушках команд `gw_sh`): при первой сборке могут
понадобиться правки опций под версию Gowin EDA. Для второго мнения RTL синтезируется и yosys:
`yosys -p "read_verilog -sv <files>; synth_gowin -top top"` (≈ 240 LUT, таблица синуса → BSRAM).

Светодиоды `synth_core`: 0–3 — GPIO прошивки (0 мигает), 4 — активность MIDI, 5 — trap процессора.
`mono_core`: 0 — мигание, 1 — событие MIDI, 2 — гейт, 3 — PLL, 4 — ЦАП включён.
Кнопки: S1 — сброс (9K: активный 0, 20K: активная 1), S2 — вход GPIO.

**Распиновка — предварительная (HO-01)**: I2S и MIDI на свободных выводах разъёмов
(9K и 20K: BCK 25, LRCK 26, DIN 27, XSMT 28, MIDI 29); UART BL702 — 9K: 17/18, 20K: 69/70;
SPI-флеш — 9K: встроенная на плате (59–62), 20K: внешняя на разъёме (73, 74, 75, 85). Перед подключением сверить со схемой
Sipeed; окончательная таблица пинов — после этапа 6.
