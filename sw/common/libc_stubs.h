/* sw/common/libc_stubs.h — minimal freestanding memcpy/memset/memcmp.
 *
 * `-ffreestanding -nostdlib` (task ABI flags) means no libc is linked, but
 * GCC is still permitted by the freestanding subset of the C standard to
 * emit implicit calls to these four functions for aggregate
 * initialization/copy and zeroing even with -fno-builtin (that flag only
 * suppresses recognizing *explicit* calls as builtins, not this codegen
 * lowering). Every freestanding target in this tree links this file so
 * struct-literal descriptor initialization (npu.h npu_descriptor_t and
 * similar) does not produce an undefined-symbol link failure.
 */
#ifndef OPENCHIP_SW_COMMON_LIBC_STUBS_H
#define OPENCHIP_SW_COMMON_LIBC_STUBS_H

#include <stddef.h>

void *memcpy(void *restrict dst, const void *restrict src, size_t n);
void *memset(void *dst, int c, size_t n);
void *memmove(void *dst, const void *src, size_t n);
int memcmp(const void *a, const void *b, size_t n);

#endif /* OPENCHIP_SW_COMMON_LIBC_STUBS_H */
