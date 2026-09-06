/* sw/common/crc32.h — CRC-32/ISO-HDLC per SYS-05:
 * "CRC is CRC-32/ISO-HDLC: reflected polynomial 0xEDB88320, init/xorout
 * 0xffffffff over exactly byte_length payload bytes."
 * Reused verbatim by LLM-06/LLM-11 (out of B1 scope) which cite the same
 * parameters.
 */
#ifndef OPENCHIP_SW_COMMON_CRC32_H
#define OPENCHIP_SW_COMMON_CRC32_H

#include <stddef.h>
#include <stdint.h>

/* One-shot CRC-32/ISO-HDLC over `len` bytes starting at `data`. */
uint32_t crc32_iso_hdlc(const void *data, size_t len);

#endif /* OPENCHIP_SW_COMMON_CRC32_H */
