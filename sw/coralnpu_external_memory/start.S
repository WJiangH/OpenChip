/* Copyright 2023 Google LLC
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *     http://www.apache.org/licenses/LICENSE-2.0
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 * CN-SW-03 freestanding equivalent of coralnpu_start.S: no constructors,
 * no libc or semihosting; loader zeros PT_LOAD BSS per CNEM-07.
 */
.option norelax
.section .text.start,"ax",@progbits
.balign 16
.global _start
.type _start,@function
_start:
    li sp, 0x00200000
    la t0, trap_handler
    csrw mtvec, t0
    li t0, 0x6600
    csrrs zero, mstatus, t0
    la t0, _ret
    li t1, 0x0badd00d
    sw t1, 0(t0)
    call main
    la t0, _ret
    sw a0, 0(t0)
    li t0, 0x20018100
    sw a0, 44(t0)
    /* All result/record stores precede this sole terminal magic store. */
    li t1, 0x434e454d
    sw t1, 0(t0)
    csrr a0, minstret
    csrr a1, minstreth
.global clean_halt
clean_halt:
    .word 0x08000073
1:  j 1b
.size _start, .-_start

.section .text.trap,"ax",@progbits
.balign 16
.global trap_handler
.type trap_handler,@function
trap_handler:
    /* No return and no register restoration; no stack dependency. */
    csrr a0, mcause
    csrr a1, mepc
    csrr a2, mtval
    li t0, 0x20018100
    li t1, 1
    sw t1, 4(t0)
    li t2, 0x20018000
    lw t3, 4(t2)
    sw t3, 8(t0)
    sw t1, 12(t0)
    sw zero, 16(t0)
    sw zero, 20(t0)
    sw zero, 24(t0)
    sw t1, 28(t0)
    sw a0, 32(t0)
    sw a1, 36(t0)
    sw a2, 40(t0)
    sw t1, 44(t0)
    sw zero, 48(t0)
    sw zero, 52(t0)
    sw zero, 56(t0)
    sw zero, 60(t0)
    la t2, _ret
    sw t1, 0(t2)
    li t1, 0x434e454d
    sw t1, 0(t0)
    .word 0x08000073
2:  j 2b
.size trap_handler, .-trap_handler

.section .bss.ret,"aw",@nobits
.balign 4
.global _ret
.type _ret,@object
.size _ret, 4
_ret: .zero 4
