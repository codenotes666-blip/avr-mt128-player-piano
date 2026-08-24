/*
 * Behavioral reconstruction of the Olimex AVR-MT128 factory test firmware.
 * Target: ATmega128 at 16 MHz.
 *
 * This is a clean AVR-GCC implementation inferred from the backed-up machine
 * code and matched against Olimex's published AVR-MT128 test source. It is not
 * guaranteed to compile byte-for-byte to the original firmware.
 */

#define F_CPU 16000000UL

#include <avr/io.h>
#include <util/delay.h>
#include <stdint.h>

#define LCD_RS PC0
#define LCD_ENABLE PC2
#define RELAY PA6
#define BUZZER_1 PE4
#define BUZZER_2 PE5

#define BUTTON_1 PA0
#define BUTTON_2 PA1
#define BUTTON_3 PA2
#define BUTTON_4 PA3
#define BUTTON_5 PA4
#define DALLAS_INPUT PA5

#define LCD_DISPLAY_ON 0x0C
#define LCD_CLEAR 0x01
#define LCD_LINE_1 0x80
#define LCD_LINE_2 0xC0

static const char startup_message[32] = "   AVR-MT-128    olimex.com/dev ";
static const char dallas_message[16] = " DALLAS PRESENT ";
static const char timer1_message[16] = "TMR1 is CLOCKED ";
static const char timer2_message[16] = "TMR2 is CLOCKED ";
static const char serial_message[16] = " olimex.com/dev ";
static const char website_message[32] = " Visit the site  www.olimex.com ";
static const char sending_message[16] = "sending to RS232";

typedef struct {
    uint8_t display_position;
} application_state_t;

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

static void lcd_write_character(char character) {
    lcd_write_byte((uint8_t)character, 1);
}

static void lcd_write_fixed(const char *text, uint8_t length, uint8_t split_line) {
    for (uint8_t index = 0; index < length; ++index) {
        if (split_line != 0 && index == 16) {
            lcd_command(LCD_LINE_2);
        }
        lcd_write_character(text[index]);
    }
}

static void lcd_clear_to_line(uint8_t line_address) {
    lcd_command(LCD_CLEAR);
    lcd_command(line_address);
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
}

static void uart1_write(uint8_t value) {
    while ((UCSR1A & _BV(UDRE1)) == 0) {
    }
    UDR1 = value;
}

static uint8_t __attribute__((unused)) uart1_read(void) {
    uint8_t status;
    do {
        do {
            status = UCSR1A;
        } while ((status & _BV(RXC1)) == 0);
    } while ((status & (_BV(FE1) | _BV(UPE1) | _BV(DOR1))) != 0);
    return UDR1;
}

static uint16_t __attribute__((unused)) adc_read(uint8_t channel) {
    ADMUX = (channel & 0x0F) | _BV(REFS0);
    ADCSRA |= _BV(ADSC);
    while ((ADCSRA & _BV(ADIF)) == 0) {
    }
    ADCSRA |= _BV(ADIF);
    return ADC;
}

static void sound_buzzer_while_pressed(void) {
    while ((PINA & _BV(BUTTON_4)) == 0) {
        PORTE &= (uint8_t)~_BV(BUZZER_1);
        PORTE |= _BV(BUZZER_2);
        _delay_us(125);
        PORTE &= (uint8_t)~_BV(BUZZER_2);
        PORTE |= _BV(BUZZER_1);
        _delay_us(125);
    }
}

static void initialize_hardware(void) {
    PORTA = 0x00;
    DDRA = _BV(RELAY);
    PORTB = 0x00;
    DDRB = 0x00;
    PORTC = 0x00;
    DDRC = 0xF7;
    PORTD = 0x00;
    DDRD = _BV(PD3);
    PORTE = 0x00;
    DDRE = _BV(BUZZER_1) | _BV(BUZZER_2);
    PORTF = 0x00;
    DDRF = 0x00;
    PORTG = 0x00;
    DDRG = 0x00;

    TCCR1A = 0x00;
    TCCR1B = 0x07;
    TCNT1 = 0;
    OCR1A = 0;
    OCR1B = 0;
    OCR1C = 0;

    TCCR2 = 0x07;
    TCNT2 = 0;
    OCR2 = 0;

    UCSR1A = 0x00;
    UCSR1B = _BV(RXEN1) | _BV(TXEN1);
    UCSR1C = _BV(UCSZ11) | _BV(UCSZ10);
    UBRR1H = 0;
    UBRR1L = 103;
}

static void show_startup_message(void) {
    lcd_command(LCD_DISPLAY_ON);
    delay_ms(10);
    lcd_clear_to_line(LCD_LINE_1);
    delay_ms(10);
    lcd_write_fixed(startup_message, sizeof(startup_message), 1);
    lcd_command(LCD_LINE_1);
}

static void reset_display(application_state_t *state, uint8_t line_address) {
    lcd_clear_to_line(line_address);
    state->display_position = 0;
}

/*
 * Consume one waiting USART1 byte and show it on the 16x2 LCD.
 *
 * Characters fill the first LCD row, then the second. After 32 characters the
 * display is cleared and writing starts over at row one. The factory firmware
 * also sends the received byte plus one back over USART1. For example, an 'A'
 * received from the PC is displayed as 'A', while 'B' is returned to the PC.
 */
static void service_uart_to_lcd(application_state_t *state) {
    /* RXC1 is set by the UART hardware when UDR1 contains a received byte. */
    if ((UCSR1A & _BV(RXC1)) == 0) {
        return;
    }

    /* A 16x2 display has 32 visible character positions. */
    if (state->display_position == 0 || state->display_position == 32) {
        reset_display(state, LCD_LINE_1);
    } else if (state->display_position == 16) {
        /* Move the LCD cursor from the end of row one to the start of row two. */
        lcd_command(LCD_LINE_2);
    }

    /* Reading UDR1 consumes the byte that was waiting in the UART receiver. */
    uint8_t received = UDR1;
    lcd_write_character((char)received);

    /* Preserve the unusual response behavior observed in the factory image. */
    uart1_write((uint8_t)(received + 1));
    ++state->display_position;
}

static void update_relay_from_button(void) {
    if ((PINA & _BV(BUTTON_1)) == 0) {
        PORTA |= _BV(RELAY);
    } else {
        PORTA &= (uint8_t)~_BV(RELAY);
    }
}

static void handle_clear_display_button(application_state_t *state) {
    if ((PINA & _BV(BUTTON_2)) == 0) {
        reset_display(state, LCD_LINE_1);
    }
}

static void handle_website_message_button(application_state_t *state) {
    if ((PINA & _BV(BUTTON_3)) == 0) {
        reset_display(state, LCD_LINE_1);
        lcd_write_fixed(website_message, sizeof(website_message), 1);
    }
}

static void handle_buzzer_button(void) {
    if ((PINA & _BV(BUTTON_4)) == 0) {
        sound_buzzer_while_pressed();
    }
}

static void handle_serial_demo_button(application_state_t *state) {
    if ((PINA & _BV(BUTTON_5)) != 0) {
        return;
    }

    reset_display(state, LCD_LINE_1);
    for (uint8_t index = 0; index < sizeof(serial_message); ++index) {
        uart1_write((uint8_t)serial_message[index]);
        lcd_write_character(sending_message[index]);
    }
}

static void service_user_controls(application_state_t *state) {
    /* Poll the five active-low buttons in the same order as the factory code. */
    update_relay_from_button();
    delay_ms(1);
    handle_clear_display_button(state);
    delay_ms(1);
    handle_website_message_button(state);
    delay_ms(1);
    handle_buzzer_button();
    delay_ms(1);
    handle_serial_demo_button(state);
    delay_ms(1);
}

static void service_dallas_presence(application_state_t *state) {
    if ((PINA & _BV(DALLAS_INPUT)) != 0) {
        return;
    }

    /* Require a sustained low level before announcing a Dallas/iButton device. */
    uint8_t stable_low_count = 250;
    while (stable_low_count != 0) {
        if ((PINA & _BV(DALLAS_INPUT)) == 0) {
            --stable_low_count;
        } else {
            stable_low_count = 250;
        }
    }

    reset_display(state, LCD_LINE_1);
    lcd_write_fixed(dallas_message, sizeof(dallas_message), 0);
}

static void service_external_clock_events(application_state_t *state) {
    /* Timer 1 and Timer 2 count pulses arriving through the FREQ input jumper. */
    if (TCNT1L >= 2 || TCNT1H != 0) {
        TCNT1 = 0;
        reset_display(state, LCD_LINE_1);
        lcd_write_fixed(timer1_message, sizeof(timer1_message), 0);
    }

    if (TCNT2 >= 2) {
        TCNT2 = 0;
        reset_display(state, LCD_LINE_2);
        lcd_write_fixed(timer2_message, sizeof(timer2_message), 0);
    }
}

int main(void) {
    application_state_t state = {0};

    initialize_hardware();
    delay_ms(100);
    lcd_initialize();
    delay_ms(10);
    show_startup_message();

    for (;;) {
        /* Cooperative polling loop reconstructed from the factory firmware. */
        service_uart_to_lcd(&state);
        service_user_controls(&state);
        service_dallas_presence(&state);
        service_external_clock_events(&state);
    }
}