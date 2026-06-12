#include "uart.h"
#include <avr/interrupt.h>
#include "midi.h"

void uart_init(uint16_t baudrate) {
	UBRR0H = (uint8_t)(baudrate >> 8);
	UBRR0L = (uint8_t)baudrate;
	UCSR0B = (1 << RXCIE0) | (1 << RXEN0);
	UCSR0C = (1 << UCSZ01) | (1 << UCSZ00);
}

ISR(USART_RX_vect) {
	midiParser(UDR0);
}
