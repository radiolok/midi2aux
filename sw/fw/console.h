/* Text console on the debug UART: parameter access and test notes without a panel.
 *   set <param> <value>   get <param>   list
 *   route <k 1..7> <src> <via> <dst> <depth>     (numbers as in hw.h, depth raw)
 *   note <n> [vel]   off <n>   help */
#ifndef CONSOLE_H
#define CONSOLE_H

#include "synth.h"

void console_init(struct synth *s);
void console_feed(char c); /* one received character */
void console_exec(char *line);

#endif
