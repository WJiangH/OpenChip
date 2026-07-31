/* Minimal freestanding UART driver, footprint-estimate skeleton only.
 * The real libc-free runtime (uart_putc, printf-lite, §4.4 IRQ glue) lands
 * in sw/runtime/ during M3 (sw/README.md); this is a stand-in with the same
 * approximate call surface so the estimate's control flow is realistic.
 */
#include "uart.h"
#include "soc1_regmap.h"

void uart_putc(char c)
{
    UART_DATA(SOC1_UART_BASE) = (uint32_t)(unsigned char)c;
}

void uart_puts(const char *s)
{
    while (*s) {
        uart_putc(*s++);
    }
}

static char hex_nibble(unsigned int v)
{
    v &= 0xFu;
    return (char)(v < 10 ? ('0' + v) : ('a' + (v - 10)));
}

void uart_put_u32_hex(unsigned int v)
{
    for (int shift = 28; shift >= 0; shift -= 4) {
        uart_putc(hex_nibble(v >> shift));
    }
}
