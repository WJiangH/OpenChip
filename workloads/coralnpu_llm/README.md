# Complete tiny-LM generation baseline

**Draft engineering workload, not execution-ready.** This profile selects the
entire pretrained **stories260K** from `karpathy/tinyllamas` to exercise complete
model execution on the pinned CoralNPU CoreAXI configuration. It selects no
production model, language-quality target or performance target. The
[contract](../../docs/spec/coralnpu_llm.md) defines the evidence required before
any full-generation claim; the [decision](../../docs/adr/0005-coralnpu-complete-tiny-lm-baseline.md)
explains the alternatives and SoC boundary.

The publisher documents training all five layers with a custom 512-token
vocabulary and supplies generation examples. This is a complete trained tiny
language model, not a shortened larger model or a random fixture. See the pinned
[training description](https://huggingface.co/karpathy/tinyllamas/blob/0bd21da7698eaf29a0d7de3992de8a46ef624add/stories260K/readme.md).

| Workload property | Selected proposal |
|---|---|
| Dimensions | Width 64, FFN 172, layers 5, query/KV heads 8/4, head width 8, vocabulary 512 |
| Context | Trained limit512; experiment capacity 40 |
| Inputs | Two prompts, batch1, at most32 input tokens including specials |
| Outputs | At most8 new tokens; at least 5 before normal stop to exercise four actual decode evaluations |
| Sampling | Target-owned greedy argmax; lowest token ID on exact tie |
| Host boundary | Tokenization, initial loading, observation and detokenization |
| Target boundary | All prefill/decode operations, all layers, KV updates, full vocabulary head and feedback |
| Initial arithmetic | Proposed scalar FP32; numerical and ISA qualification OPEN |

The [profile](profile.json) pins the publisher revision and expected artifact
hashes. These are source metadata identities, not evidence that downloaded
weights, tokenizer behavior or inference passed. No weights or tokenizer files
are included. The initial intake needs only the model `.bin`, `tok512.bin` and
`tok512.model`, totaling **1,070,412 bytes**; it does not require pickle loading.

Starting prompt proposals are `Once upon a time,` and `Lily went to the park`.
Exact token IDs, BOS/EOS behavior and adequate decode length remain OPEN until
independent tokenizer/reference qualification. A fixture that reaches EOS too
early must be replaced before scoring; forcing continuation is not acceptable.
Full512 logits are retained at every evaluated prefill/decode position. Serial
prefill is allowed, so the bounded workload needs at most39 evaluations per run
(32 prompt positions plus7 feedback evaluations for8 generated tokens).

The complete legacy model file is 1,056,540 bytes, including header and stored
RoPE tables. It exceeds the old1 MiB external aperture before KV/code/scratch.
The new contract therefore proposes a distinct2 MiB map. Reproduce analytical
counts with `python3 explore/coralnpu_llm/calculate.py`; its
[worksheet](../../explore/coralnpu_llm/README.md) states the assumptions.

The publisher's model card labels the model repository MIT. File-specific
licenses still matter: pinned `llama2.c/tokenizer.py` carries a Llama2 Community
License header despite the repository MIT license. Do not copy that wrapper
under a blanket MIT assumption. Independently authored host code may use a
separately qualified SentencePiece dependency with the custom tokenizer; exact
dependency notices and behavior remain an intake requirement.
