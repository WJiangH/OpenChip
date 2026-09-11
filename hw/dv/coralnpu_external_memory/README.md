# CoralNPU external-memory verification

Independent public-pin host, AXI memory responder, byte scoreboard and arithmetic
oracle for [CN-EXTMEM-01 v0.4](../../../docs/spec/coralnpu_external_memory.md).
The [workload](../../../workloads/coralnpu_external_memory/README.md) defines the
expected arithmetic. Hardware, software and their review have separate owners.
The checker derives expectations from that contract and workload; software
metadata supplies only ELF identity, placement and designated symbol addresses.
Read separation is a convention, not a filesystem-enforced boundary.

The native launcher consumes newly built [CoralNPU IP](../../ip/coralnpu/README.md)
and [software artifacts](../../../sw/coralnpu_external_memory/README.md).
It requires an explicit runtime manifest and a software review bound to the
current manifest and contract. The pinned generic wrapper accepts external
absolute models using `../` followed by the absolute filename; the launcher
applies that spelling while retaining the canonical absolute model path for
build identity checks. Each fresh output also contains a deterministic
`sitecustomize.py` that puts the validated runtime package roots before Bazel's
same-named empty packages, preserving all other Python paths. The normal wrapper
bootstrap and runner stay unchanged. The startup hook is a mandatory hashed
artifact; missing or modified hook bytes cannot produce launcher PASS. No installed container name, previous cache path,
historical result or private authorization document is a prerequisite. Missing
or mismatched inputs fail before execution. The native model, top identity and
source pin are bound to the primary build receipt; the auxiliary receipt binds
that exact primary receipt and source, plus an observed dependency inventory for
the generated top, parameter header, Python, wrapper, runner and libraries.
Observed dependencies are distinguished from exported target outputs. Importing these files establishes
no new DUT result and does not transfer previous execution acceptance.

## Run the CPU controls

From the repository root:

```console
make -f hw/dv/coralnpu_external_memory/native.mk controls
```

These synthetic controls exercise responder protocol and byte semantics,
watchdogs, ELF loading, independent scoring, negative completion and reset
witnesses. Packaging controls reject stale identities, wrong/empty/malformed
cocotb XML, skipped/failed tests, process failure and incomplete evidence.
They never execute a simulator or software fixture.

## Run one native profile

Use a case-sensitive Linux environment provisioned by the IP native build entry.
The launcher runs in that environment; container transport, if used, belongs to
the caller. Follow the IP and software READMEs to obtain a runtime JSON and a
software manifest. An independent software reviewer supplies a JSON with:

```json
{
  "verdict": "APPROVED",
  "software_manifest_sha256": "<SHA-256 of the current software manifest>",
  "contract_sha256": "cdb0a147cc770f595bc2ee07b5bc589d7f38ad8500341e950078c786b2cb9b15"
}
```

That document records CNEM-29 review; writing an approval label alone is not an
independent review or acceptance mechanism. Retain the review's supporting
source/map/disassembly findings separately. Run within the environment owner's
current resource reservation and the separately authorized execution budget.

```console
python3 -B hw/dv/coralnpu_external_memory/launch.py \
  --runtime /absolute/build/runtime.json \
  --software /absolute/software/manifest.json \
  --software-review /absolute/review/software-review.json \
  --profile POS-S0-P0 \
  --output /absolute/receipts/new-run \
  --wall-seconds 115
```

Equivalent explicit Make entry:

```console
make -f hw/dv/coralnpu_external_memory/native.mk sim \
  RUNTIME=/absolute/build/runtime.json SOFTWARE=/absolute/software/manifest.json \
  SOFTWARE_REVIEW=/absolute/review/software-review.json PROFILE=POS-S0-P0 \
  OUTPUT=/absolute/receipts/new-run WALL_SECONDS=115
```

Output must be new. One invocation runs one profile; it never builds or silently
skips an unavailable runtime. There is deliberately no module `Makefile`, so
reference `make sim` and its coverage gates do not discover this native flow.
Wall time is explicitly selected in 1–115 seconds. Timeout cleanup shares one
absolute 5-second deadline across TERM, KILL and reaping. An unreaped child is
recorded as UNKNOWN and cannot pass. The clock watchdogs remain exactly those in the contract.
Receipts record configured wall bounds, elapsed time, child CPU usage, selected
environment, candidate/source/configuration/artifact hashes and separate process,
XML and checker outcomes. Keep raw runs outside public history.

## Profiles and retained checks

`profiles.json` is the reproducible schedule selection, with seed 42 throughout.
Symbol addresses are resolved anew from the reviewed software manifest.

| Profiles | Software | Schedule and selection |
| --- | --- | --- |
| `POS-S0-P0`, `POS-S17-P0` | positive | Both salts, always-ready requests and 1-cycle eligible responses |
| `POS-S0-P1`, `POS-S17-P1` | positive | Both salts, independent 0–7 request stalls and 1–15 response delays |
| `ERR-FETCH-SLVERR`, `ERR-FETCH-DECERR` | fetch | One selected fetch error at `0x200ff000` |
| `ERR-LOAD-SLVERR`, `ERR-LOAD-DECERR` | load | One selected aligned load error at `0x200ff000` |
| `ERR-STORE-SLVERR`, `ERR-STORE-DECERR` | store | One selected aligned store error, no memory mutation |
| `ERR-UNMAPPED-LOAD` | unmapped | Decode error at `0x21000000` |
| `RESET-AR` | positive | Abort first entry fetch with R withheld, cold reload salt 17 |
| `RESET-WRITE-HALF` | positive | Abort startup return AW with W withheld, cold reload salt 17 |

Error and reset profiles use P0. The positive scoreboard retains all 97 outputs,
4,330 input bytes, 388 output write bytes, seven probe write bytes, 64 guard bytes,
record comparison and observed startup/actual-return stores. Negative completion
requires the sentinel stores to finish before handler return stores, all 36
mandatory record bytes and all four handler-return bytes before final magic,
and the exact cause/PC/value for the designated case. No return store after
final magic can pass. Both families retain their 32 additional observation edges.
No threshold, quiet window or P1 exercise requirement is relaxed by packaging.

Positive, error and coordinated-reset verdicts must be reported separately.
A parsed exact one-test cocotb success, process exit zero, complete artifacts and
checker PASS are all necessary for launcher PASS. A checker FAIL is retained
even when process or artifact collection also fails. Raw cycle traces, input and
final images, reset epochs and runtime identities remain available for review.
This is neither AXI/ISA or coverage closure nor SoC, LLM, physical or tapeout
acceptance.
