/*
 * Piano Hall Sensor
 * Olimex AVR-MT128 + KY-024 linear magnetic Hall sensor
 *
 * KY-024 A0 -> 1 kOhm series resistor -> ADC0/PF0
 * KY-024 G  -> board GND
 * KY-024 +  -> board +5V
 * Optional 100 nF capacitor: ADC0/PF0 to GND for noise filtering
 */

#define F_CPU 16000000UL

#include <avr/io.h>
#include <util/delay.h>
#include <stdint.h>

#define LCD_RS PC0
#define LCD_ENABLE PC2
#define BUZZER_1 PE4
#define BUZZER_2 PE5

#define LCD_DISPLAY_ON 0x0C
#define LCD_CLEAR 0x01
#define LCD_LINE_1 0x80
#define LCD_LINE_2 0xC0

typedef struct {
    const char *name;
    uint16_t half_period_us;
} note_t;

static const note_t notes[] = {
    {"C4", 1911}, {"D4", 1703}, {"E4", 1517}, {"F4", 1432},
    {"G4", 1276}, {"A4", 1136}, {"B4", 1012}, {"C5", 956},
};

static void delay_ms(uint16_t milliseconds) {
    while (milliseconds-- != 0) {
        _delay_ms(1);
    }
}

static void delay_microseconds(uint16_t microseconds) {
    while (microseconds-- != 0) {
        _delay_us(1);
    }
}

static void lcd_enable_pulse(void) {
    PORTC |= _BV(LCD_ENABLE);
    _delay_us(5);
    PORTC &= (uint8_t)~_BV(LCD_ENABLE);
}

static void lcd_write_nibble(uint8_t nibble, uint8_t data_mode) {
    PORTC = (PORTC & 0x0F) | (nibble & 0xF0);
    if (data_mode != 0) PORTC |= _BV(LCD_RS);
    else PORTC &= (uint8_t)~_BV(LCD_RS);
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
    while (*text != '\0') lcd_character(*text++);
}

static void lcd_initialize(void) {
    PORTC &= (uint8_t)~_BV(LCD_RS);
    delay_ms(110);
    lcd_write_nibble(0x30, 0); delay_ms(10);
    lcd_write_nibble(0x30, 0); delay_ms(10);
    lcd_write_nibble(0x30, 0); delay_ms(10);
    lcd_write_nibble(0x20, 0);
    lcd_command(LCD_DISPLAY_ON);
    lcd_command(LCD_CLEAR);
}

static void adc_initialize(void) {
    /* AVCC is the 5 V ADC reference; divide the ADC clock by 128. */
    ADMUX = _BV(REFS0);
    ADCSRA = _BV(ADEN) | _BV(ADPS2) | _BV(ADPS1) | _BV(ADPS0);
}

static uint16_t read_hall_adc(void) {
    ADMUX = _BV(REFS0) | 0;
    ADCSRA |= _BV(ADSC);
    while ((ADCSRA & _BV(ADSC)) != 0) {
    }
    return ADC;
}

static uint16_t calibrate_hall_baseline(void) {
    uint32_t total = 0;
    for (uint8_t sample = 0; sample < 64; ++sample) {
        total += read_hall_adc();
        delay_ms(4);
    }
    return (uint16_t)(total / 64);
}

static uint16_t absolute_difference(uint16_t left, uint16_t right) {
    return left >= right ? left - right : right - left;
}

static uint8_t field_to_note(uint16_t reading, uint16_t baseline) {
    uint16_t magnitude = absolute_difference(reading, baseline);
    const uint16_t dead_zone = 12;
    const uint16_t step = 28;

    if (magnitude <= dead_zone) return 0;
    uint16_t index = (magnitude - dead_zone) / step;
    if (index >= (sizeof(notes) / sizeof(notes[0]))) index = (sizeof(notes) / sizeof(notes[0])) - 1;
    return (uint8_t)index;
}

static void play_note(const note_t *note, uint8_t cycles) {
    for (uint8_t cycle = 0; cycle < cycles; ++cycle) {
        PORTE |= _BV(BUZZER_1);
        PORTE &= (uint8_t)~_BV(BUZZER_2);
        delay_microseconds(note->half_period_us);
        PORTE &= (uint8_t)~_BV(BUZZER_1);
        PORTE |= _BV(BUZZER_2);
        delay_microseconds(note->half_period_us);
    }
    PORTE &= (uint8_t)~(_BV(BUZZER_1) | _BV(BUZZER_2));
}

static void show_note(const note_t *note, uint16_t reading) {
    lcd_command(LCD_LINE_1);
    lcd_text("Hall Piano      ");
    lcd_command(LCD_LINE_2);
    lcd_text("Note ");
    lcd_text(note->name);
    lcd_text(" ADC ");
    lcd_character((char)('0' + (reading / 1000) % 10));
    lcd_character((char)('0' + (reading / 100) % 10));
    lcd_character((char)('0' + (reading / 10) % 10));
    lcd_character((char)('0' + reading % 10));
    lcd_text(" ");
}

int main(void) {
    DDRC = 0xF7;
    DDRE |= _BV(BUZZER_1) | _BV(BUZZER_2);
    DDRF &= (uint8_t)~_BV(PF0);

    lcd_initialize();
    adc_initialize();
    lcd_command(LCD_LINE_1);
    lcd_text("Keep magnet away");
    lcd_command(LCD_LINE_2);
    lcd_text("Calibrating...  ");
    uint16_t baseline = calibrate_hall_baseline();

    uint8_t previous_note = 0xFF;
    for (;;) {
        uint16_t reading = read_hall_adc();
        uint8_t note_index = field_to_note(reading, baseline);
        if (note_index != previous_note) {
            show_note(&notes[note_index], reading);
            previous_note = note_index;
        }
        play_note(&notes[note_index], 8);
    }
}