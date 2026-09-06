/* sw/common/crc32.c — CRC-32/ISO-HDLC, bit-at-a-time (no table: ROM budget is
 * tight and this runs once over <= 0x30000 bytes at boot). Reflected
 * polynomial 0xEDB88320, init 0xffffffff, xorout 0xffffffff — see SYS-05.
 */
#include "crc32.h"

uint32_t crc32_iso_hdlc(const void *data, size_t len) {
    const uint8_t *p = (const uint8_t *)data;
    uint32_t crc = 0xFFFFFFFFu;
    for (size_t i = 0; i < len; i++) {
        crc ^= (uint32_t)p[i];
        for (int b = 0; b < 8; b++) {
            uint32_t mask = (uint32_t)(-(int32_t)(crc & 1u));
            crc = (crc >> 1) ^ (0xEDB88320u & mask);
        }
    }
    return crc ^ 0xFFFFFFFFu;
}
