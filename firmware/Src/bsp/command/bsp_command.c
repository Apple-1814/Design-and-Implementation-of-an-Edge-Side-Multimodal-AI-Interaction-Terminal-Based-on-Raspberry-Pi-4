#include "bsp_command.h"
#include "led\bsp_led.h"
#include "lcd\bsp_lcd.h"
#include "usart\bsp_usart.h"
#include "adc/bsp_adc.h"
#include "pwm/bsp_pwm.h"

#include <stdarg.h>
#include <stdio.h>
#include <string.h>

#define CMD_RX_SIZE 256u
#define CMD_LINE_SIZE 128u

static volatile uint8_t s_rx[CMD_RX_SIZE];
static volatile uint16_t s_head = 0u;
static volatile uint16_t s_tail = 0u;

static char s_line[CMD_LINE_SIZE];
static uint16_t s_line_len = 0u;
static uint8_t s_led_state = 0u;
static uint8_t s_pwm_duty = 0u;
static uint8_t s_pwm_duty2 = 0u;

static void cmd_send(const char *text)
{
    if (text == 0)
    {
        return;
    }
    (void)HAL_UART_Transmit(&huart1, (uint8_t *)text, (uint16_t)strlen(text), 200u);
}

static void cmd_sendf(const char *fmt, ...)
{
    char buf[128];
    va_list ap;

    va_start(ap, fmt);
    (void)vsnprintf(buf, sizeof(buf), fmt, ap);
    va_end(ap);
    cmd_send(buf);
}

static void cmd_parse(char *line)
{
    int id;
    int on;
    int line_no;
    unsigned int mask;
    char text[64];

    if (line[0] == '\0')
    {
        return;
    }

    if (strcmp(line, "PING") == 0)
    {
        cmd_send("OK PONG\n");
        return;
    }

    if (strcmp(line, "LED?") == 0)
    {
        cmd_sendf("OK LED %02X\n", (unsigned int)s_led_state);
        return;
    }

    if (sscanf(line, "LED %d %d", &id, &on) == 2)
    {
        if (id < 1 || id > 8)
        {
            cmd_send("ERR LED_ID\n");
            return;
        }
        if (on != 0)
        {
            s_led_state |= (uint8_t)(1u << (id - 1));
        }
        else
        {
            s_led_state &= (uint8_t)~(1u << (id - 1));
        }
        LED_Disp(s_led_state);
        cmd_sendf("OK LED %d %d\n", id, (on != 0) ? 1 : 0);
        return;
    }

    if (sscanf(line, "LEDALL %x", &mask) == 1)
    {
        s_led_state = (uint8_t)mask;
        LED_Disp(s_led_state);
        cmd_sendf("OK LEDALL %02X\n", (unsigned int)s_led_state);
        return;
    }

    if (sscanf(line, "LCD %d %63[^\n]", &line_no, text) == 2)
    {
        if (line_no < 0 || line_no > 9)
        {
            cmd_send("ERR LCD_LINE\n");
            return;
        }
        LCD_DisplayStringLine((u8)(line_no * 24), (u8 *)text);
        cmd_send("OK LCD\n");
        return;
    }

    if (strcmp(line, "LCDCLR") == 0)
    {
        LCD_Clear(White);
        cmd_send("OK LCDCLR\n");
        return;
    }

    if (strcmp(line, "ADC?") == 0)
    {
        cmd_sendf("OK ADC %u\n", (unsigned int)getADC1());
        return;
    }

    if (strcmp(line, "ADC2?") == 0)
    {
        cmd_sendf("OK ADC2 %u\n", (unsigned int)getADC2());
        return;
    }

    if (strcmp(line, "PWM?") == 0)
    {
        cmd_sendf("OK PWM 1 %u\n", (unsigned int)s_pwm_duty);
        return;
    }

    if (strcmp(line, "PWM2?") == 0)
    {
        cmd_sendf("OK PWM 2 %u\n", (unsigned int)s_pwm_duty2);
        return;
    }

    {
        int ch;
        int duty;
        if (sscanf(line, "PWM %d %d", &ch, &duty) == 2)
        {
            if ((ch != 1 && ch != 2) || duty < 0 || duty > 100)
            {
                cmd_send("ERR PWM_ARG\n");
                return;
            }
            if (ch == 1)
            {
                PWM_SetDuty((uint8_t)duty);
                s_pwm_duty = (uint8_t)duty;
            }
            else
            {
                PWM_SetDuty2((uint8_t)duty);
                s_pwm_duty2 = (uint8_t)duty;
            }
            cmd_sendf("OK PWM %d %d\n", ch, duty);
            return;
        }
    }

    cmd_send("ERR UNKNOWN\n");
}

void CMD_Init(void)
{
    s_head = 0u;
    s_tail = 0u;
    s_line_len = 0u;
    s_led_state = 0u;
    LED_Disp(0u);
    cmd_send("READY\n");
}

void CMD_FeedByte(uint8_t byte)
{
    uint16_t next = s_head + 1u;

    if (next >= CMD_RX_SIZE)
    {
        next = 0u;
    }
    if (next != s_tail)
    {
        s_rx[s_head] = byte;
        s_head = next;
    }
}

void CMD_Proc(void)
{
    char ch;

    while (s_tail != s_head)
    {
        ch = (char)s_rx[s_tail];
        s_tail++;
        if (s_tail >= CMD_RX_SIZE)
        {
            s_tail = 0u;
        }

        if (ch == '\r')
        {
            continue;
        }
        if (ch == '\n')
        {
            s_line[s_line_len] = '\0';
            cmd_parse(s_line);
            s_line_len = 0u;
        }
        else if (s_line_len < (CMD_LINE_SIZE - 1u))
        {
            s_line[s_line_len] = ch;
            s_line_len++;
        }
        else
        {
            s_line_len = 0u;
            cmd_send("ERR OVERFLOW\n");
        }
    }
}
