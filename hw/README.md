# Железо: несущая плата и панель

Проект KiCad схемы — [`kicad/`](kicad/README.md) (сгенерирован по `schematic.md`, цепи сверены скриптом; PDF —
[`kicad/avk_synth.pdf`](kicad/avk_synth.pdf)). Дальше здесь будут плата (Tang Nano 20K, ЦАП, АЦП входов, ОУ, MIDI, СИНХР, органы
управления) и чертёж панели 120×90 мм. Схему и разводку рисует автор проекта.

![Структурная схема](../img/readme/block-diagram.png)

Исходные данные:
- **принципиальная схема по узлам** (листы KiCad, позиционные обозначения, номиналы, подключение по выводам, расчёты) —
  [`schematic.md`](schematic.md);
- требования к узлам, номиналы, открытые вопросы `HO-xx` — [`.plans/fpga-synth/hw-requirements.md`](../.plans/fpga-synth/hw-requirements.md);
- структурная схема — [`.plans/fpga-synth/block-diagram.svg`](../.plans/fpga-synth/block-diagram.svg)
  (генерируется `.plans/fpga-synth/tools-gen-block-diagram.py`);
- эскиз панели — [`.plans/fpga-synth/panel-sketch.svg`](../.plans/fpga-synth/panel-sketch.svg);
- трек «железо» H1–H4 — [`.plans/fpga-synth/plan.md`](../.plans/fpga-synth/plan.md).

Предварительная распиновка макета (этап 0) — в `fpga/boards/*/*.cst`, окончательная — после этапа 6 (HO-01).
