/* sw/common/compiler_barrier.h — NPU-08 "compiler barrier" driver step.
 *
 * This is a *compiler* ordering barrier only (prevents the compiler from
 * reordering/eliding MMIO-adjacent stores/loads across the barrier); it is
 * not a hardware FENCE. dependencies.md: "FENCE is decoded, FENCE.I is
 * unsupported" — we deliberately do not emit a hardware fence instruction
 * here, since ordering between the CPU and the NPU's independent AXI
 * initiator is already established by the CSR SUBMIT/STATUS handshake
 * (NPU-05/NPU-06), not by any CPU-local memory fence.
 */
#ifndef OPENCHIP_SW_COMMON_COMPILER_BARRIER_H
#define OPENCHIP_SW_COMMON_COMPILER_BARRIER_H

#define SW_COMPILER_BARRIER() __asm__ volatile ("" ::: "memory")

#endif /* OPENCHIP_SW_COMMON_COMPILER_BARRIER_H */
