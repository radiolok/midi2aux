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
    midi/uart_rx.sv    UART 8N1, 31250 бод
  boards/
    tang_nano_9k/      top.sv, pll_sys.v (rPLL), .cst, .sdc, build.tcl (gw_sh)
    tang_nano_20k/     то же для 20K
  sim/
    tb_stub_core.cpp   тестбенч Verilator: MIDI → ядро → декодер I2S → WAV + JSON
    check_stub.py      анализ WAV: частота, THD, форма, сравнение с моделью → pass/fail
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
| `make sim` | сборка тестбенча, симуляция 0.3 с, проверки `check_stub.py` |
| `make model` | pytest моделей + эталонные WAV в `build/model/` |
| `make fw` | прошивка RISC-V → `build/sw/fw.{elf,bin,hex,map}` |
| `make test` | `lint` + `model` + `sim` — то же, что проверяет CI (кроме `fw`) |
| `make all` | `test` + `fw` |
| `make luts` | перегенерировать `rtl/audio/sine_quarter_rom.sv` из модели |
| `make plots` | `sim` + `refs` и обновить графики в `sim/img/`, `model/img/` |
| `make bitstream-9k`, `make bitstream-20k` | Gowin EDA, только локально |

Параметры: `make sim SYS_CLK_HZ=99000000 FS_HZ=48000 TONE_HZ=440 SIM_DURATION=0.3`.

Результаты в `build/sim/`: `stub_core.wav` (стерео, 24 бит — можно послушать), `stub_core.png`
(осциллограмма и спектры), `stub_core_tb.json` (сводка тестбенча), `stub_core_report.json` (проверки).
В CI те же файлы — артефакты `sim-stub-core`, `model-refs`, `firmware` на странице запуска workflow.

## Что проверяется

Тестбенч (`tb_stub_core.cpp`, код возврата ≠ 0 при ошибке):
- формат I2S на уровне выводов, как его принимает ЦАП: LRCK/DIN меняются только по спаду BCK,
  32 такта BCK на слот, MSB через такт после фронта LRCK, биты ниже `DATA_W` — нули, период BCK постоянный;
- MIDI: байты из файла стимулов передаются на `midi_rx` с таймингом 31250 бод; принятые ядром байты
  совпадают с отправленными.

`check_stub.py`:
- fs = sys_clk / (128 · BCK_HALF), отклонение от 48 кГц ≤ 3 %;
- L (синус): основной тон 440 Гц ± 0.5 %, THD ≤ −70 дБ, THD+N ≤ −60 дБ, пик 0.99…1.0 FS;
- R (пила): основной тон ± 0.5 %, H2/H1 = −6 ± 1 дБ;
- оба канала **побитово** совпадают с моделью `synthmodel.nco`.

### Формат стимулов MIDI

Текст, строка — `<время_мс> <байт hex> [<байт hex> …]`, `#` — комментарий. Байты строки идут
подряд с указанного времени (или сразу после предыдущего сообщения, если оно ещё передаётся).
Пример — `sim/stimuli/stub_midi.txt`. Входы ВХ1/ВХ2 из файлов подключатся к тестбенчу вместе
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
make bitstream-9k     # → build/gowin/9k/impl/pnr/avk_synth_9k.fs
make bitstream-20k    # → build/gowin/20k/impl/pnr/avk_synth_20k.fs
openFPGALoader -b tangnano9k build/gowin/9k/impl/pnr/avk_synth_9k.fs      # в SRAM
openFPGALoader -b tangnano20k -f build/gowin/20k/impl/pnr/avk_synth_20k.fs # во флеш
```

Или в GUI: новый проект под нужный кристалл (9K: `GW1NR-LV9QN88PC6/I5`, 20K: `GW2AR-LV18QN88C8/I7`),
добавить файлы из `rtl/files.f` и из `boards/<плата>/`, top module — `top`,
Verilog Language — SystemVerilog 2017.

`build.tcl` проверен только «всухую» (на заглушках команд `gw_sh`): при первой сборке могут
понадобиться правки опций под версию Gowin EDA. Для второго мнения RTL синтезируется и yosys:
`yosys -p "read_verilog -sv <files>; synth_gowin -top top"` (≈ 240 LUT, таблица синуса → BSRAM).

Светодиоды: 0 — мигание 1 Гц, 1 — переключается на каждый байт MIDI, 2 — PLL захвачен,
3 — ЦАП включён (XSMT). Кнопка — сброс (9K: активный 0, 20K: S1, активная 1).

**Распиновка I2S и MIDI — предварительная (HO-01)**: взяты свободные выводы разъёмов
(9K и 20K: BCK 25, LRCK 26, DIN 27, XSMT 28, MIDI 29). Перед подключением сверить со схемой
Sipeed; окончательная таблица пинов — после этапа 6.
