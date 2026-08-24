/*
 * KY-024 analog-output test for the Olimex AVR-MT128.
 *
 * Wiring:
 *   KY-024 A0 -> 1 kOhm series resistor -> ADC header pin 3 (ADC0/PF0)
 *   KY-024 G  -> EXT2 pin 1 (GND)
 *   KY-024 +  -> EXT2 pin 2 (+5 V)
 *
 * The LCD continuously displays: AD Value:<0-1023>
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

static void delay_ms(uint16_t milliseconds) {
    while (milliseconds-- != 0) {
        _delay_ms(1);
    }
}

static void lcd_enable_pulse(void) {
    PORTC |= _BV(LCD_ENABLE);
    _delay_us(5);
    PORTC &= (uint8_t)~_BV(LCD_ENABLE);
}

static void lcd_write_nibble(uint8_t nibble, uint8_t data_mode) {
    PORTC = (PORTC & 0x0F) | (nibble & 0xF0);
    if (data_mode != 0) {
        PORTC |= _BV(LCD_RS);
    } else {
        PORTC &= (uint8_t)~_BV(LCD_RS);
    }
    lcd_enable_pulse();
}

static void lcd_write_byte(uint8_t value, uint8_t data_mode) {
    delay_ms(2);
    lcd_write_nibble(value, data_mode);
    lcd_write_nibble((uint8_t)(value << 4), data_mode);
}

static void lcd_command(uint8_t command) {
    lcd_write_byte(command, 0);
}

static void lcd_character(char character) {
    lcd_write_byte((uint8_t)character, 1);
}

static void lcd_text(const char *text) {
    while (*text != '\0') {
        lcd_character(*text++);
    }
}

static void lcd_initialize(void) {
    PORTC &= (uint8_t)~_BV(LCD_RS);
    delay_ms(110);

    lcd_write_nibble(0x30, 0);
    delay_ms(10);
    lcd_write_nibble(0x30, 0);
    delay_ms(10);
    lcd_write_nibble(0x30, 0);
    delay_ms(10);
    lcd_write_nibble(0x20, 0);

    lcd_command(LCD_DISPLAY_ON);
    lcd_command(LCD_CLEAR);
    lcd_command(LCD_LINE_1);
}

static void adc_initialize(void) {
    /* Use AVCC (the board's 5 V rail) as the ADC reference and select ADC0. */
    ADMUX = _BV(REFS0);

    /* Enable the ADC and divide 16 MHz by 128 for a 125 kHz ADC clock. */
    ADCSRA = _BV(ADEN) | _BV(ADPS2) | _BV(ADPS1) | _BV(ADPS0);

    /* Discard the first conversion after enabling the ADC. */
    ADCSRA |= _BV(ADSC);
    while ((ADCSRA & _BV(ADSC)) != 0) {
    }
}

static uint16_t read_adc0(void) {
    ADCSRA |= _BV(ADSC);
    while ((ADCSRA & _BV(ADSC)) != 0) {
    }
    return ADC;
}

static void lcd_unsigned_decimal(uint16_t value) {
    char digits[5];
    uint8_t count = 0;

    do {
        digits[count++] = (char)('0' + (value % 10));
        value /= 10;
    } while (value != 0);

    while (count != 0) {
        lcd_character(digits[--count]);
    }
}

static void display_adc_value(uint16_t value) {
    lcd_command(LCD_LINE_1);
    lcd_text("AD Value:");
    lcd_unsigned_decimal(value);

    /* Erase characters left behind when the new value has fewer digits. */
    lcd_text("   ");
}

int main(void) {
    /* PC0, PC1, PC2 and PC4-PC7 drive the onboard LCD. PC3 remains input. */
    PORTC = 0x00;
    DDRC = 0xF7;

    /* ADC0/PF0 receives the KY-024 analog output. */
    PORTF &= (uint8_t)~_BV(PF0);
    DDRF &= (uint8_t)~_BV(PF0);

    lcd_initialize();
    adc_initialize();

    for (;;) {
        display_adc_value(read_adc0());
        delay_ms(100);
    }
}