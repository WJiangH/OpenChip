"""Analytical worksheet only: no weights, model, simulator or compiler.

Dimensions and formulas: workloads/coralnpu_llm/profile.json and this directory's
README.md. The forty-position bound intentionally exceeds the workload's thirty-
nine evaluated positions per run. All integers count logical elements or bytes.
"""

import json

D, M, L, H, HK, V, C, T = 64, 172, 5, 8, 4, 512, 512, 40
K = D * HK // H
parts = {
    "embedding_tied_head": V * D,
    "attention_norms": L * D,
    "q": L * D * D,
    "k": L * K * D,
    "v": L * K * D,
    "o": L * D * D,
    "ffn_norms": L * D,
    "w1": L * M * D,
    "w2": L * D * M,
    "w3": L * M * D,
    "final_norm": D,
}
parameters = sum(parts.values())
rope = 2 * C * (D // H // 2) * 4
# Serial live buffers; scalars, stack, alignment and guards are separate.
scratch = (4 * D + 2 * K + 2 * M + H * T + V) * 4
linear_macs = L * (2 * D * D + 2 * D * K + 3 * D * M) + V * D
regions = [
    ("code", 0x20000000, 0x40000),
    ("model_bin", 0x20040000, 0x140000),
    ("kv", 0x20180000, 0x10000),
    ("scratch", 0x20190000, 0x10000),
    ("results", 0x201A0000, 0x20000),
    ("descriptor", 0x201C0000, 0x10000),
    ("reserve", 0x201D0000, 0x30000),
]
report = {
    "dimensions": {
        "d": D, "ffn": M, "layers": L, "query_heads": H, "kv_heads": HK,
        "head_dim": D // H, "kv_width": K, "vocab": V,
        "trained_context": C, "workload_capacity": T,
    },
    "parameter_parts": parts,
    "unique_parameters": parameters,
    "fp32_parameter_bytes": 4 * parameters,
    "legacy_header_bytes": 28,
    "legacy_rope_bytes": rope,
    "legacy_file_bytes": 28 + 4 * parameters + rope,
    "legacy_file_excess_over_1MiB": 28 + 4 * parameters + rope - 2**20,
    "kv_bytes_at40": 2 * L * T * K * 4,
    "logits_bytes_per_position": V * 4,
    "logits_bytes_per_run40positions": T * V * 4,
    "serial_live_scratch_bytes": scratch,
    "linear_MAC_per_position": linear_macs,
    "attention_MAC_per_position_at40": 2 * L * D * T,
    "upper_MAC_per_position_at40": linear_macs + 2 * L * D * T,
    "two_run_80position_MAC_bound": 80 * (linear_macs + 2 * L * D * T),
    "two_run_full_logit_bytes_bound": 80 * V * 4,
    "streamed_weight_bytes_per_position": linear_macs * 4,
    "gemma_publisher_parameters": 268098176,
    "gemma_fp32_payload_bytes": 268098176 * 4,
    "gemma_remaining_below_1GiB": 2**30 - 268098176 * 4,
    "initial_acquisition_three_artifacts_bytes": 1056540 + 6227 + 7645,
    "regions": [
        {"name": name, "base": hex(base), "end_exclusive": hex(base + size),
         "bytes": size}
        for name, base, size in regions
    ],
}
assert parameters == 260032 and report["legacy_file_bytes"] == 1056540
assert scratch == 5984 and report["kv_bytes_at40"] == 51200
assert all(base + size <= 2**32 for _, base, size in regions)
assert all(a[1] + a[2] == b[1] for a, b in zip(regions, regions[1:]))
print(json.dumps(report, indent=2))
