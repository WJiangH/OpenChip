# Change order 1.0-rc2 → 1.0-rc3

2026-09-05 · chief-architect. Scope: seven precise interface/serialization/numeric closures only. All seven are ruled **spec-bug**; no hardware failure or completed target test is alleged. Original rc2 change order/review02 records are retained. rc3-review-input-hashes.json binds the three independent pure reports and pre-edit package hashes. Reviewers' accepted findings are not reopened. Independent rc3 re-review is still required before declaring this contract ready for handoff.

| Finding /source | Architect ruling and concrete correction | Affected artifacts /downstream owners |
|---|---|---|
| RTL RC2-01 | Add local→dot command_last; local derives final row/group from its descriptor, dot forwards with result.last under backpressure |npu.md,contract.json /local,dot,DMA RTL and independent DV |
| RTL RC2-02 | CPU wrapper receives common rst_n plus core-local reset; sticky metadata uses common only |system.md,contract.json /CPU wrapper,system RTL,DV/formal |
| DV RC2-01 | Both CPU and NPU offer AW no later than first W, without waiting for AWREADY; targets still tolerate W handshake before AW; retained offered writes survive error/stop |axi.md,npu.md,system.md,contract.json /initiators,fabric,DV/formal |
| DV RC2-02 | Use known offered/accepted aligned address; absent corresponding AR/AW is address0, including early-W timeout |axi.md,system.md,contract.json /monitor,system,DV |
| SW-RC2-01 | SiLU d=round(1+exp(-x)), inv=round(1/d), silu=round(x*inv), hidden=round(silu*up); no algebraic x/d substitution |workload.md /runtime,independent scalar reference,DV |
| SW-RC2-02 | SYS-05 CRC parameters, validated blob_bytes intervals including header/directory/internal padding/data; runtime input-header CRCs authoritative; expected_bytes equality; validate lengths first |workload.md /exporter,loader,independent parser DV |
| SW-RC2-03 | Matrix data_bytes=rows*row_stride excludes scales; scale length4*rows*ceil(cols/64); norm data_bytes=rows*cols*4; exact identity shapes and all disjoint regions enforced |workload.md /exporter,loader,DV |

No requirement IDs, CSR offsets, deployment header/descriptor byte layouts, legal numerical formats, quality thresholds, clock/bandwidth assumptions, resource counts or model identities change. The binary ABI remains major1; rc3 resolves intended interpretation before freeze. Requirement obligations, release labels and manifest hashes are synchronized. Existing arithmetic budgets are rerun unchanged because these fixes add no mathematical work or stored payload bytes. No RTL/DV/SW implementation or tests were read or modified.

Sources: [RTL report](reviews/rtl-review-rc2.md), [DV report](reviews/dv-review-rc2.md), [SW report](reviews/sw-review-rc2.md). Gate state remains architecture-review only; S1/P1/FPGA and all hardware acceptance are outside this change order.
