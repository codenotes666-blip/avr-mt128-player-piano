/*
 * AVR-MT128 player-piano controller.
 *
 * Verified wiring:
 *   KY-024 D0 -> PD5 / EXT1 pin 12
 *   Pi pin 8 TX -> MT128 TTL third contact from left, RXD1 / PD2
 *   MT128 TTL right contact, TXD1 / PD3 -> 1k/2k divider -> Pi pin 10 RX
 *   Pi pin 6 GND -> MT128 TTL second contact from left, GND
 *   MT128 TTL left contact, +5V, remains disconnected from the Pi
 *
 * UART: 115200 8N1, newline-terminated ASCII commands.
 * Commands: BEEP, RELAY_ON, RELAY_OFF, AUTO_RELEASE_ON,
 *           AUTO_RELEASE_OFF, LCD <text>, PLAY, STATUS.
 */

#define F_CPU 16000000UL

#include <avr/io.h>
#include <avr/eeprom.h>
#include <util/delay.h>
#include <stdint.h>
#include <string.h>

#define LCD_RS PC0
#define LCD_ENABLE PC2
#define LCD_DISPLAY_ON 0x0C
#define LCD_CLEAR 0x01
#define LCD_LINE_1 0x80
#define LCD_LINE_2 0xC0

#define HALL_D0_PIN PD5
#define CENTER_BUTTON PA2
#define BOTTOM_BUTTON PA4
#define RELAY_PIN PA6
#define BUZZER_1 PE4
#define BUZZER_2 PE5
#define HALL_HOLD_TICKS 2000
#define COMMAND_LENGTH 40
#define AUTO_RELEASE_MAGIC 0xC7
#define AUTO_RELEASE_ENABLED 0xA5
#define AUTO_RELEASE_DISABLED 0x5A

static uint8_t EEMEM eeprom_auto_release_magic;
static uint8_t EEMEM eeprom_auto_release;

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

static void lcd_command(uint8_t command) {
    lcd_byte(command, 0);
    if (command == LCD_CLEAR) delay_ms(2);
}
static void lcd_character(char character) { lcd_byte((uint8_t)character, 1); }

static void lcd_text(const char *text) {
    while (*text != '\0') lcd_character(*text++);
}

static void lcd_initialize(void) {
    PORTC = 0x00;
    DDRC = 0xF7;
    delay_ms(110);
    lcd_nibble(0x30, 0); delay_ms(10);
    lcd_nibble(0x30, 0); delay_ms(10);
    lcd_nibble(0x30, 0); delay_ms(10);
    lcd_nibble(0x20, 0);
    lcd_command(LCD_DISPLAY_ON);
    lcd_command(LCD_CLEAR);
}

static void lcd_screen(const char *text) {
    lcd_command(LCD_CLEAR);
    lcd_command(LCD_LINE_1);
    for (uint8_t index = 0; index < 32; ++index) {
        if (index == 16) lcd_command(LCD_LINE_2);
        lcd_character(*text != '\0' ? *text++ : ' ');
    }
}

static void display_hall_state(uint8_t magnet_detected) {
    lcd_command(LCD_LINE_2);
    if (magnet_detected != 0) {
        lcd_text("D0:1 MAGNET ON  ");
    } else {
        lcd_text("D0:0 MAGNET OFF ");
    }
}

static void beep(void) {
    for (uint16_t cycle = 0; cycle < 240; ++cycle) {
        PORTE |= _BV(BUZZER_1);
        PORTE &= (uint8_t)~_BV(BUZZER_2);
        _delay_us(250);
        PORTE &= (uint8_t)~_BV(BUZZER_1);
        PORTE |= _BV(BUZZER_2);
        _delay_us(250);
    }
    PORTE &= (uint8_t)~(_BV(BUZZER_1) | _BV(BUZZER_2));
}

static void uart_initialize(void) {
    UCSR1A = _BV(U2X1);
    UBRR1H = 0;
    UBRR1L = 16;
    UCSR1B = _BV(RXEN1) | _BV(TXEN1);
    UCSR1C = _BV(UCSZ11) | _BV(UCSZ10);
}

static void uart_character(char character) {
    while ((UCSR1A & _BV(UDRE1)) == 0) {
    }
    UDR1 = (uint8_t)character;
}

static void uart_text(const char *text) {
    while (*text != '\0') uart_character(*text++);
}

static void uart_line(const char *text) {
    uart_text(text);
    uart_text("\r\n");
}

static uint8_t uart_read_command(char *command, uint8_t *length) {
    while ((UCSR1A & _BV(RXC1)) != 0) {
        char character = (char)UDR1;
        if (character == '\r' || character == '\n') {
            if (*length != 0) {
                command[*length] = '\0';
                *length = 0;
                return 1;
            }
        } else if (*length < COMMAND_LENGTH - 1) {
            command[(*length)++] = character;
        } else {
            *length = 0;
            uart_line("ERROR COMMAND TOO LONG");
        }
    }
    return 0;
}

static uint8_t relay_is_on(void) {
    return (PORTA & _BV(RELAY_PIN)) != 0;
}

static void relay_set(uint8_t enabled) {
    if (enabled != 0) PORTA |= _BV(RELAY_PIN);
    else PORTA &= (uint8_t)~_BV(RELAY_PIN);
}

static uint8_t load_auto_release(void) {
    if (eeprom_read_byte(&eeprom_auto_release_magic) != AUTO_RELEASE_MAGIC) {
        return 1;
    }
    return eeprom_read_byte(&eeprom_auto_release) != AUTO_RELEASE_DISABLED;
}

static void save_auto_release(uint8_t enabled) {
    eeprom_update_byte(
        &eeprom_auto_release,
        enabled != 0 ? AUTO_RELEASE_ENABLED : AUTO_RELEASE_DISABLED
    );
    eeprom_update_byte(&eeprom_auto_release_magic, AUTO_RELEASE_MAGIC);
}

static void process_command(
    const char *command,
    uint8_t magnet_detected,
    uint8_t *playing,
    uint8_t *auto_release
) {
    if (strcmp(command, "BEEP") == 0) {
        beep();
        uart_line("STATUS BEEP");
        uart_line("OK");
    } else if (strcmp(command, "RELAY_ON") == 0) {
        if (magnet_detected != 0) {
            uart_line("ERROR MAGNET ACTIVE");
        } else {
            relay_set(1);
            uart_line("STATUS RELAY ON");
            uart_line("OK");
        }
    } else if (strcmp(command, "RELAY_OFF") == 0) {
        relay_set(0);
        *playing = 0;
        uart_line("STATUS RELAY OFF");
        uart_line("OK");
    } else if (strcmp(command, "AUTO_RELEASE_ON") == 0) {
        *auto_release = 1;
        save_auto_release(*auto_release);
        uart_line("STATUS AUTO RELEASE ON");
        uart_line("OK");
    } else if (strcmp(command, "AUTO_RELEASE_OFF") == 0) {
        *auto_release = 0;
        save_auto_release(*auto_release);
        uart_line("STATUS AUTO RELEASE OFF");
        uart_line("OK");
    } else if (strncmp(command, "LCD", 3) == 0 &&
               (command[3] == '\0' || command[3] == ' ')) {
        lcd_screen(command[3] == ' ' ? command + 4 : "");
        uart_line("STATUS LCD UPDATED");
        uart_line("OK");
    } else if (strncmp(command, "PLAY", 4) == 0 &&
               (command[4] == '\0' || command[4] == ' ')) {
        if (magnet_detected != 0) {
            uart_line("ERROR MAGNET ACTIVE");
        } else {
            relay_set(1);
            *playing = 1;
            uart_line("STATUS RELAY ON");
            uart_line("STARTED");
        }
    } else if (strcmp(command, "STATUS") == 0) {
        uart_line(relay_is_on() != 0 ? "STATUS RELAY ON" : "STATUS RELAY OFF");
        uart_line(magnet_detected != 0 ? "STATUS HALL TRIP" : "STATUS HALL CLEAR");
        uart_line(*auto_release != 0 ? "STATUS AUTO RELEASE ON" : "STATUS AUTO RELEASE OFF");
        uart_line("OK");
    } else {
        uart_line("ERROR UNKNOWN COMMAND");
    }
}

int main(void) {
    uint8_t displayed_hall_state = 0xFF;
    uint8_t previous_button_pressed = 0;
    uint8_t previous_relay_state = 0;
    uint8_t playing = 0;
    uint8_t auto_release = load_auto_release();
    uint8_t command_length = 0;
    uint16_t hall_hold_ticks = 0;
    char command[COMMAND_LENGTH];

    DDRA = (DDRA & (uint8_t)~(_BV(CENTER_BUTTON) | _BV(BOTTOM_BUTTON))) | _BV(RELAY_PIN);
    PORTA = (PORTA | _BV(CENTER_BUTTON) | _BV(BOTTOM_BUTTON)) & (uint8_t)~_BV(RELAY_PIN);
    DDRD &= (uint8_t)~_BV(HALL_D0_PIN);
    PORTD |= _BV(HALL_D0_PIN);
    DDRE |= _BV(BUZZER_1) | _BV(BUZZER_2);
    PORTE &= (uint8_t)~(_BV(BUZZER_1) | _BV(BUZZER_2));
    lcd_initialize();
    uart_initialize();

    lcd_command(LCD_LINE_1);
    lcd_text("PIANO SENSOR    ");
    display_hall_state(0);
    uart_line("STATUS READY");

    for (;;) {
        uint8_t magnet_detected = (PIND & _BV(HALL_D0_PIN)) != 0;
        uint8_t button_pressed = (PINA & _BV(CENTER_BUTTON)) == 0;
        uint8_t release_pressed = (PINA & _BV(BOTTOM_BUTTON)) == 0;
        if (uart_read_command(command, &command_length) != 0) {
            process_command(command, magnet_detected, &playing, &auto_release);
        }

        if (magnet_detected != 0) {
            hall_hold_ticks = HALL_HOLD_TICKS;
        } else if (hall_hold_ticks != 0) {
            --hall_hold_ticks;
        }

        if ((magnet_detected != 0 && auto_release != 0) || release_pressed != 0) {
            relay_set(0);
        }

        if (button_pressed != 0 && previous_button_pressed == 0 &&
            magnet_detected == 0 && release_pressed == 0) {
            relay_set(1);
        }
        previous_button_pressed = button_pressed;

        uint8_t hall_state = hall_hold_ticks != 0;
        if (hall_state != displayed_hall_state) {
            display_hall_state(hall_state);
            if (displayed_hall_state != 0xFF) {
                uart_line(hall_state != 0 ? "STATUS HALL TRIP" : "STATUS HALL CLEAR");
            }
            if (hall_state != 0 && displayed_hall_state != 0xFF) {
                beep();
                if (playing != 0) {
                    playing = 0;
                    uart_line("COMPLETE");
                }
            }
            displayed_hall_state = hall_state;
        }

        uint8_t relay_state = relay_is_on();
        if (relay_state != previous_relay_state) {
            uart_line(relay_state != 0 ? "STATUS RELAY ON" : "STATUS RELAY OFF");
            previous_relay_state = relay_state;
        }
        _delay_us(100);
    }
}