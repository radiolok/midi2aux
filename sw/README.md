# Прошивка софт-процессора (PicoRV32, RV32IMC)

Этап 0 — заглушка: проверяет тулчейн и линкер-скрипт. Драйверы, загрузчик, меню и распределитель
голосов появятся с этапа 2.

```
link.ld          код и данные в BSRAM с адреса 0, 32 КБ, стек в конце
src/start.S      сброс: gp, sp, очистка .bss, main()
src/main.c       «hello» в UART и мигание LED (регистры предварительные)
include/hw.h     карта памяти (trs.md 8.2)
tools/bin2hex.py BIN → HEX (32-битные слова) для инициализации BSRAM через $readmemh
```

Сборка: `make fw` из корня → `build/sw/fw.{elf,bin,hex,map}`. Тулчейн: `riscv-none-elf-` (xPack) или
`riscv64-unknown-elf-` (Ubuntu: `apt install gcc-riscv64-unknown-elf`), выбирается автоматически;
явно — `make fw CROSS=riscv-none-elf-`. Стандартная библиотека не используется (`-nostdlib`),
поэтому multilib-сборка libc под rv32 не нужна.
