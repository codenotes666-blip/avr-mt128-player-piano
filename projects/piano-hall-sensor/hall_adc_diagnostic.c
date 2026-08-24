/*
 * AVR-MT128 ADC0 signal diagnostic.
 *
 * LCD row 1: A0:xxxx
 * LCD row 2: Lo:xxxx Hi:xxxx
 *
 * A true KY-024 analog output should idle near mid-scale and move smoothly.
 * A signal that alternates between near 0 and 1023 is behaving like D0.
 */

#define F_CPU 16000000UL

#include <avr/io.h>
#include <util/delay.h>
#include <stdint.h>

#define LCD_RS PC0
#define LCD_ENABLE PC2
#define LCD_DISPLAY_ON 0x0C
#define LCD_CLEAR 0x01
#define LCD_LINE_1 0x80
#define LCD_LINE_2 0xC0

static void delay_ms(uint16_t milliseconds) {
    while (milliseconds-- != 0) _delay_ms(1);
}

static void lcd_enable_pulse(void) {
    PORTC |= _BV(LCD_ENABLE);
    _delay_us(5);
    PORTC &= (uint8_t)~_BV(LCD_ENABLE);
}

static void lcd_nibble(uint8_t value, uint8_t data_mode) {
    PORTC = (PORTC & 0x0F) | (value & 0xF0);
    if (data_mode != 0) PORTC |= _BV(LCD_RS);
    else PORTC &= (uint8_t)~_BV(LCD_RS);
    lcd_enable_pulse();
}

static void lcd_byte(uint8_t value, uint8_t data_mode) {
    delay_ms(2);
    lcd_nibble(value, data_mode);
    lcd_nibble((uint8_t)(value << 4), data_mode);
}

static void lcd_command(uint8_t command) { lcd_byte(command, 0); }
static void lcd_character(char character) { lcd_byte((uint8_t)character, 1); }

static void lcd_text(const char *text) {
    while (*text != '\0') lcd_character(*text++);
}

static void lcd_uint4(uint16_t value) {
    lcd_character(value >= 1000 ? (char)('0' + value / 1000) : ' ');
    lcd_character(value >= 100 ? (char)('0' + (value / 100) % 10) : ' ');
    lcd_character(value >= 10 ? (char)('0' + (value / 10) % 10) : ' ');
    lcd_character((char)('0' + value % 10));
}

static void lcd_initialize(void) {
    PORTC &= (uint8_t)~_BV(LCD_RS);
    delay_ms(110);
    lcd_nibble(0x30, 0); delay_ms(10);
    lcd_nibble(0x30, 0); delay_ms(10);
    lcd_nibble(0x30, 0); delay_ms(10);
    lcd_nibble(0x20, 0);
    lcd_command(LCD_DISPLAY_ON);
    lcd_command(LCD_CLEAR);
}

static void adc_initialize(void) {
    ADMUX = _BV(REFS0);
    ADCSRA = _BV(ADEN) | _BV(ADPS2) | _BV(ADPS1) | _BV(ADPS0);

}

static uint16_t adc_conversion(uint8_t channel) {
    ADMUX = _BV(REFS0) | (channel & 0x07);
    ADCSRA |= _BV(ADSC);
    while ((ADCSRA & _BV(ADSC)) != 0) {
    }
    return ADC;
}

static void display_channels(void) {
    uint32_t total = 0;
    uint16_t low = 1023;
    uint16_t high = 0;

    for (uint8_t sample = 0; sample < 64; ++sample) {
        uint16_t reading = adc_conversion(0);
        total += reading;
        if (reading < low) low = reading;
        if (reading > high) high = reading;
        _delay_us(100);
    }
    uint16_t average = (uint16_t)(total / 64);

    lcd_command(LCD_LINE_1);
    lcd_text("A0:"); lcd_uint4(average);
    lcd_text("        ");

    lcd_command(LCD_LINE_2);
    lcd_text("Lo:"); lcd_uint4(low);
    lcd_text(" Hi:"); lcd_uint4(high);
    lcd_character(' ');
}

int main(void) {
    PORTC = 0x00;
    DDRC = 0xF7;
    PORTF &= (uint8_t)~(_BV(PF0) | _BV(PF1) | _BV(PF2) | _BV(PF3));
    DDRF &= (uint8_t)~(_BV(PF0) | _BV(PF1) | _BV(PF2) | _BV(PF3));

    lcd_initialize();
    adc_initialize();

    for (;;) {
        display_channels();
        delay_ms(150);
    }
}