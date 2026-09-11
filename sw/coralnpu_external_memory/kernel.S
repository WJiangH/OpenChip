/* Copyright 2026 Google LLC
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *     http://www.apache.org/licenses/LICENSE-2.0
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 * CN-SW-03 adaptation of rvv_int8_matmul.cc: one tail-bounded path,
 * one signed product per K iteration, no bundled loads or unbounded stores.
 */
.section .text.kernel,"ax",@progbits
.balign 16
.global rvv_gemv_int8
.type rvv_gemv_int8,@function
/* a0=A, a1=B, a2=C, a3=K, a4=N; standard vector caller-saved ABI. */
rvv_gemv_int8:
    li t0, 0
1:
    bgeu t0, a4, 4f
    sub t1, a4, t0
    vsetvli t1, t1, e8, m1, ta, ma
    /* e8/m1, e16/m2, e32/m4 all have the same VLMAX (16 here). */
    vsetvli zero, t1, e32, m4, ta, ma
    vmv.v.i v16, 0
    mv t2, a0
    add t3, a1, t0
    li t4, 0
2:
    bgeu t4, a3, 3f
    lb t5, 0(t2)
    vsetvli zero, t1, e8, m1, ta, ma
    vle8.v v4, (t3)
    vwmul.vx v8, v4, t5
    vsetvli zero, t1, e16, m2, ta, ma
    vwadd.wv v16, v16, v8
    addi t2, t2, 1
    add t3, t3, a4
    addi t4, t4, 1
    j 2b
3:
    slli t6, t0, 2
    add t6, a2, t6
    vsetvli zero, t1, e32, m4, ta, ma
    vse32.v v16, (t6)
    add t0, t0, t1
    j 1b
4:
    ret
.size rvv_gemv_int8, .-rvv_gemv_int8
