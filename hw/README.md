# Железо: несущая плата и панель

Здесь будут проект KiCad несущей платы (Tang Nano 20K, ЦАП, АЦП входов, ОУ, MIDI, СИНХР, органы
управления) и чертёж панели 120×90 мм. Схему и разводку рисует автор проекта.

![Структурная схема](../img/readme/block-diagram.png)

Исходные данные:
- требования к узлам, номиналы, открытые вопросы `HO-xx` — [`.plans/fpga-synth/hw-requirements.md`](../.plans/fpga-synth/hw-requirements.md);
- структурная схема — [`.plans/fpga-synth/block-diagram.svg`](../.plans/fpga-synth/block-diagram.svg)
  (генерируется `.plans/fpga-synth/tools-gen-block-diagram.py`);
- эскиз панели — [`.plans/fpga-synth/panel-sketch.svg`](../.plans/fpga-synth/panel-sketch.svg);
- трек «железо» H1–H4 — [`.plans/fpga-synth/plan.md`](../.plans/fpga-synth/plan.md).

Предварительная распиновка макета (этап 0) — в `fpga/boards/*/*.cst`, окончательная — после этапа 6 (HO-01).
