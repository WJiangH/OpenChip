# CoralNPU native IP

This entry imports the unmodified [Google CoralNPU source](https://github.com/google-coral/coralnpu)
at commit `561c59d33fea8a02e7f1062956ec77740e0eb955`. [ip.json](ip.json)
binds the Git commit, complete source tree, exact Git archive, Bazel version and
selected native build targets. The [integration boundary](../../../docs/adr/0004-coralnpu-integration-boundary.md)
and [external-memory contract](../../../docs/spec/coralnpu_external_memory.md)
define the selected configuration and experiment scope. Source is fetched on demand; generated RTL and
third-party build caches are not checked into OpenChip.

The selected model is `RvvCoreMiniHighmemAxi`. Its upstream Chisel/Bazel flow is
retained. Reference-design Wishbone, synchronous reset and Yosys conventions do
not change the upstream IP. Building this model does not establish its DV,
full-SoC, FPGA, physical-design or tapeout acceptance.

## Source and model build

Build on Linux x86-64 with a **case-sensitive filesystem**, Python 3.12 or newer, Git and
Bazel **8.6.0**. Follow the pinned upstream source's native prerequisites for
Clang, Java and system libraries. A macOS bind-mounted source directory is not
suitable: upstream contains both `SRAM.scala` and `Sram.scala`. A Linux Docker
volume or Linux filesystem can hold the extracted source. The scripts reject a
case-insensitive destination before extracting files.

From a fresh OpenChip checkout on Linux, choose your own writable scratch path:

```bash
mkdir -p /tmp/openchip-coral
python3 hw/ip/coralnpu/source.py fetch --dest /tmp/openchip-coral/source
python3 hw/ip/coralnpu/source.py verify --source /tmp/openchip-coral/source
python3 hw/ip/coralnpu/source.py build --source /tmp/openchip-coral/source \
  --output-root /tmp/openchip-coral/build --timeout 900
```

`fetch` obtains the exact commit from the public Git remote into a temporary
bare repository, checks its tree, generates a Git archive and checks its
SHA-256 **before extraction**. It then recomputes every Git blob and directory
hash, including executable modes and symlinks. Only that verified tree is
installed in the new destination. Existing destinations are never overwritten.
An optional `--archive /path/to/exact.tar` skips the network; it must have the
same pinned archive SHA-256. No private archive or pre-existing cache is required.

`verify` rejects changed, missing or extra files, including `.git`, local Bazel
configuration and generated output. Keep build outputs separate from source.

`build` first verifies source and the Bazel version, then invokes the fixed
`//tests/cocotb:rvv_core_mini_highmem_axi_model` target in Bazel batch mode.
The upstream `.bazelrc` remains active; user and system Bazel RC files are disabled.
The output root must be new and outside source. By default its Bazel cache is
new; optional `--cache-root /your/owned/cache` explicitly reuses a cache while
keeping a new attempt log and receipt. Do not point it at another active or
accepted runtime cache. Source links, repository cache,
and Bazel cache remain separate from other builds; downloads follow the pinned
upstream WORKSPACE repository rules. It requests at most four concurrent Bazel
jobs, four local CPU resources and 12 GiB local memory resources. These Bazel
settings are scheduling hints: enforce hard CPU/memory limits on the enclosing
container or job. The wall-time bound is 1–900 seconds plus at most 13 seconds for two five-second
process-group termination windows and bounded process inspections. A reaped
leader alone never establishes descendant exit; receipts distinguish exited
groups, zombies with no live members, and unknown/live groups. A cold build may exceed this bound. Failed or timed
out attempts retain logs and are not successful builds.

The output root contains `build.log`, `build.bep.json` and `receipt.json` with
source identity, the exact command, elapsed time, status and SHA-256 hashes of
reported build artifacts. The BEP and artifact paths locate newly built model
outputs for downstream DV consumers. No DUT runs as part of this command.
The source is verified again after a successful build. Generated artifacts are
bound to this build receipt, not to historic binaries from another environment.

Agents first follow the repository [environment entry](../../../flow/README.md)
and coordinate any shared runtime reservation. Those private environment
records are optional machine setup, not required public source inputs.

## Native runtime and software tools

After the model build attempt exits, the separate auxiliary entry builds the
upstream generic cocotb wrapper and obtains the upstream-pinned RISC-V compiler
archive in that same owned cache. It never reruns the model target:

```bash
python3 hw/ip/coralnpu/source.py runtime-build --source /tmp/openchip-coral/source \
  --build-root /tmp/openchip-coral/build --output-root /tmp/openchip-coral/runtime-build
python3 hw/ip/coralnpu/source.py runtime --source /tmp/openchip-coral/source \
  --build-root /tmp/openchip-coral/build --runtime-root /tmp/openchip-coral/runtime-build \
  --output /tmp/openchip-coral/runtime.json
```

The auxiliary build has its own 180-second bound and retained receipt. Its
fixed targets are `@rules_hdl//cocotb:cocotb_wrapper` and
`@toolchain_coralnpu_v2//:all_files`, plus
`@coralnpu_pip_deps_cocotb//:pkg` for the declared native Python closure. The
compiler archive SHA-256 is in `ip.json`
and the pinned upstream `WORKSPACE`. Both native build receipts must report
completion before `runtime` can resolve a runtime manifest. This manifest maps
the newly built model, generated top/header, interpreter, generic wrapper,
runner, shared libraries and toolchain to their actual paths and hashes.
It also supplies the named Python environment needed by the standalone wrapper,
including all eight package roots declared by the pinned cocotb/pytest dependency
closure in upstream `third_party/python/requirements.bzl`. Their actual files
are hash-bound in the auxiliary observed inventory. A model build alone only
needs the cocotb native library and does not fetch that Python closure.
The software driver consumes `toolchain_root`; DV consumes the model and runtime
fields. `model_argument` contains the native wrapper spelling `../` followed
by the absolute model path; plain absolute `--model` is not supported by its
runfiles lookup. Launch from the supplied `cwd` and retain the supplied wrapper
bootstrap. Missing or ambiguous artifacts fail closed. Resolution is not an
actual-child environment probe or a DUT result. Downstream launchers must check
the hashes, perform their bounded preflight and pass the library directory to
the actual runner child.

The native bootstrap prepends Bazel runfiles package paths. Its generated empty
`rules_hdl/cocotb/__init__.py` can shadow the complete pinned cocotb package.
The runner replaces child `PYTHONPATH` with the wrapper interpreter's `sys.path`,
so setting `--extra_env PYTHONPATH` does not correct that order. A downstream
launcher must create a deterministic `sitecustomize.py` in its fresh run
output, prepend the validated package roots from `environment.PYTHONPATH` to
`sys.path` while retaining all other entries, and put that output directory
first in the outer `PYTHONPATH`. This preserves the native bootstrap and applies
the same ordering at wrapper and child interpreter startup. Record the generated
hook's bytes and hash; do not overwrite an existing run output or silently
replace another selected startup hook. The bounded actual-runner-child preflight
must import `cocotb` and `cocotb.logging` from the hash-bound wheel and record
their origins and hashes. Loader inspection alone does not establish Python
package resolution or embedded simulator startup.

## Dependencies and licenses

[LICENSE.upstream](LICENSE.upstream) is the unchanged upstream Apache-2.0
license. The acquired tree retains all upstream copyright headers, vendored
files, patches and dependency recipes. See [NOTICE.md](NOTICE.md) for the
source and dependency notice boundary. This import makes no source changes.

## Checks

```bash
python3 -m unittest discover -s hw/ip/coralnpu -p 'test_*.py'
```

These CPU checks exercise source-integrity and invocation failures. They do not
run Chisel, compile a simulator or establish a hardware result. This native flow
is explicitly invoked; it is not automatically included in the reference
`make lint`, `make sim`, `make formal` or physical flow targets.
