#ifndef UART_H
#define UART_H

#include <avr/io.h>

#define UART_BAUD_SELECT(baudRate, xtalCpu) ((xtalCpu) / ((baudRate) * 16L) - 1)

void uart_init(uint16_t baudrate);

#endif
