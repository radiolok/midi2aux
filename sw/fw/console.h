/* Text console on the debug UART: parameter access and test notes without a panel.
 *   set <param> <value>   get <param>   list
 *   route <k 1..7> <src> <via> <dst> <depth>     (numbers as in hw.h, depth raw)
 *   note <n> [vel]   off <n>   screen (text on the display)   panel (encoders, knobs)   help
 *   avk   cal <1|2> zero|<mV>   mem <word> [value]
 *   sd (mount)   ls   save <n>   load <n>   fwupdate (FIRMWARE.BIN -> flash) */
#ifndef CONSOLE_H
#define CONSOLE_H

#include "storage.h"
#include "synth.h"
#include "ui.h"

void console_init(struct synth *s, struct ui *u); /* u may be 0 */
void console_set_storage(struct storage *st, struct sd sd); /* SD card access for the commands */
void console_feed(char c); /* one received character */
void console_exec(char *line);

#endif
