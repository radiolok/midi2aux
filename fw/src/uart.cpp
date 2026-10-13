#include "uart.h"
#include <avr/interrupt.h>
#include "midi.h"

void uart_init(uint16_t baudrate) {
	UBRR0H = (uint8_t)(baudrate >> 8);
	UBRR0L = (uint8_t)baudrate;
	UCSR0B = (1 << RXCIE0) | (1 << RXEN0);
	UCSR0C = (1 << UCSZ01) | (1 << UCSZ00);
}

#ifdef POLY_VOICES
// Poly mode: the ISR only queues the byte (~25 cycles) so the sample ISR is
// never held off by MIDI parsing; uart_poll() runs the parser in main loop.
static volatile uint8_t rxBuf[16];
static volatile uint8_t rxHead;
static uint8_t rxTail;

ISR(USART_RX_vect) {
	uint8_t h = rxHead;
	rxBuf[h] = UDR0;
	rxHead = (h + 1) & 15;
}

void uart_poll(void) {
	while (rxTail != rxHead) {
		uint8_t b = rxBuf[rxTail];
		rxTail = (rxTail + 1) & 15;
		midiParser(b);
	}
}
#else
ISR(USART_RX_vect) {
	midiParser(UDR0);
}
#endif
