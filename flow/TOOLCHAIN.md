# Toolchain provenance — what is installed on the dev host, from where, and how the flow finds it

Host: macOS (Darwin 25.2, Apple Silicon / arm64). Repo root is `$REPO`. Every path
below is relative to it unless absolute. Nothing here is fetched by `make`; each tool
was installed once by the orchestrator on the dates given, and `flow/versions.mk`
records the pins. If you are on another machine, run the "Reproduce" block of each
section. Verify hashes after download — do not trust a copy of this file.

| Tool | Version installed | Source | Install method | Location | Pin status |
|---|---|---|---|---|---|
| Verilator | 5.051 devel (v5.050-99-gf8fb1d664) | YosysHQ OSS CAD Suite build 2026-07-26 | tarball unpack (pre-existing, P0) | `~/tools/oss-cad-suite/bin` | pinned by suite tag |
| Yosys | 0.67+94 (7defa5186) | same suite | same | same | pinned by suite tag |
| SymbiYosys (sby) + solvers | suite 2026-07-26 | same suite | same | same | pinned by suite tag |
| Icarus (iverilog) | suite 2026-07-26 | same suite | same | same | pinned by suite tag |
| Verible lint | **not installed** | — | the darwin-arm64 suite build ships no `verible-*` | — | open (FLOW-004) |
| riscv-none-elf-gcc | 14.2.0-3 (GCC 14.2.0) | xPack, GitHub release | tarball unpack, 2026-09-05 | `.toolcache/xpack-riscv-none-elf-gcc-14.2.0-3/` | pinned by version + tarball sha256 |
| Spike (riscv-isa-sim) | reports `1.1.1-dev` | riscv-software-src Homebrew tap, formula `riscv-isa-sim` | `brew install` (bottle), 2026-09-05 | `/opt/homebrew/Cellar/riscv-isa-sim/main/bin/spike` → `/opt/homebrew/bin/spike` | **unpinned** (FLOW-001) |
| RISCOF | 1.25.3 | PyPI | `pip install riscof==1.25.3` into `.venv`, 2026-09-05 | `.venv/bin/riscof` | pinned by version |
| cocotb | 2.0.1 | PyPI (`requirements.txt`) | `.venv` (pre-existing, P0) | `.venv` | pinned |
| Python | 3.13.2 | system/Homebrew | pre-existing | `.venv` base | — |
| Docker | 29.5.2 | Docker Desktop | pre-existing | — | — |
| LibreLane | 3.0.5 by image digest | ghcr.io/librelane/librelane | Docker pull (pre-existing, P0) | image cache | pinned by digest (`versions.mk`) |
| sky130A PDK | ciel-managed | (pre-existing, P0) | `~/.ciel` | — | see `versions.mk` |

## How the Makefile finds them

`Makefile` prepends `TOOLPATH` to `PATH` inside every recipe (Apple's GNU Make 3.81
ignores an exported PATH for direct-exec'd recipes — P0 finding):

```make
TOOLPATH := $(CURDIR)/.venv/bin:$(HOME)/tools/oss-cad-suite/bin:$(CURDIR)/.toolcache/xpack-riscv-none-elf-gcc-$(RISCV_GCC_VERSION)/bin
```

Consequences: (1) `make …` works from the repo root or any worktree that has
`.venv` and `.toolcache` (worktrees under `.local-designs/b1/*` symlink both to the
main checkout's copies: `ln -s $REPO/.toolcache .toolcache; ln -s $REPO/.venv .venv`);
(2) calling a tool outside `make` needs the explicit path or `PATH=…` prefix;
(3) `spike` is the one tool found via the ordinary system PATH (`/opt/homebrew/bin`),
not via `TOOLPATH`.

## 1. OSS CAD Suite (Verilator, Yosys, sby, iverilog) — pre-existing since P0

- Tag `2026-07-26`, file `~/tools/oss-cad-suite-darwin-arm64-20260726.tgz`, unpacked to
  `~/tools/oss-cad-suite/` (`VERSION` file reads `20260726`).
- Release page: https://github.com/YosysHQ/oss-cad-suite-build/releases/tag/2026-07-26
- Reproduce:
  ```bash
  mkdir -p ~/tools && cd ~/tools
  curl -LO https://github.com/YosysHQ/oss-cad-suite-build/releases/download/2026-07-26/oss-cad-suite-darwin-arm64-20260726.tgz
  tar xzf oss-cad-suite-darwin-arm64-20260726.tgz     # creates ./oss-cad-suite
  ~/tools/oss-cad-suite/bin/verilator --version && ~/tools/oss-cad-suite/bin/yosys -V
  ```
- The tarball's sha256 was not recorded at P0; record it if you re-download (FLOW-005).
- Verible is absent from this build; `make lint` runs Verilator only. AGENTS.md's
  "Verilator + Verible" wording overstates the gate until Verible is added.

## 2. xPack riscv-none-elf-gcc 14.2.0-3 — installed 2026-09-05

- Release: https://github.com/xpack-dev-tools/riscv-none-elf-gcc-xpack/releases/tag/v14.2.0-3
- Asset: `xpack-riscv-none-elf-gcc-14.2.0-3-darwin-arm64.tar.gz`, 331,541,233 bytes,
  **sha256 `e76e86b8c500f8e92b3b4ff7b0444cfbf3b218515f322929e0744ec3b9ed80a8`**
  (computed locally after download; an earlier `versions.mk` line carried a
  mistyped value `e08754e8…` — corrected in the same commit as this file).
- Installed under the repo, not system-wide: `.toolcache/` (git-ignored via
  `.toolcache/` in `.gitignore`); 32 `riscv-none-elf-*` binaries.
- Reproduce:
  ```bash
  cd $REPO && mkdir -p .toolcache && cd .toolcache
  curl -sL -o xpack-riscv-none-elf-gcc-14.2.0-3-darwin-arm64.tar.gz \
    https://github.com/xpack-dev-tools/riscv-none-elf-gcc-xpack/releases/download/v14.2.0-3/xpack-riscv-none-elf-gcc-14.2.0-3-darwin-arm64.tar.gz
  echo "e76e86b8c500f8e92b3b4ff7b0444cfbf3b218515f322929e0744ec3b9ed80a8  xpack-riscv-none-elf-gcc-14.2.0-3-darwin-arm64.tar.gz" | shasum -a 256 -c
  tar xzf xpack-riscv-none-elf-gcc-14.2.0-3-darwin-arm64.tar.gz
  ./xpack-riscv-none-elf-gcc-14.2.0-3/bin/riscv-none-elf-gcc --version
  ```
- Used with `-march=rv32im -mabi=ilp32` (soft-float); `sw/common/build.mk` holds the flags.

## 3. Spike (riscv-isa-sim) — installed 2026-09-05, UNPINNED

- Homebrew third-party tap `riscv-software-src/riscv` (the RISC-V International
  software org; Homebrew labels every non-core tap "Untrusted"). Formula
  `/opt/homebrew/Library/Taps/riscv-software-src/homebrew-riscv/riscv-isa-sim.rb`
  declares `url "https://github.com/riscv/riscv-isa-sim.git"`, `version "main"`,
  `depends_on "dtc"` — i.e. it tracks the `main` branch and the installed bottle
  does **not** expose the upstream commit (no git metadata in the Cellar; `spike
  --help` prints `1.1.1-dev`).
- Commands that were run:
  ```bash
  brew tap riscv-software-src/riscv
  brew install riscv-software-src/riscv/riscv-isa-sim      # installed the prebuilt bottle
  ```
- Why this is not good enough for the compliance gate: RISCOF results against an
  unpinned reference model are not reproducible. **FLOW-001**: before `make compliance`
  is trusted, build Spike from source at a recorded commit and put that commit in
  `versions.mk` `SPIKE_COMMIT`. Suggested procedure (not yet done):
  ```bash
  brew install dtc
  git clone https://github.com/riscv-software-src/riscv-isa-sim.git ~/tools/riscv-isa-sim
  cd ~/tools/riscv-isa-sim && git checkout <chosen commit or tag>   # record it
  mkdir build && cd build && ../configure --prefix=$HOME/tools/spike && make -j && make install
  # then: SPIKE_COMMIT := <commit>  and add $(HOME)/tools/spike/bin to TOOLPATH
  brew uninstall riscv-isa-sim   # avoid two spikes on PATH
  ```
- RISCOF also needs the `riscv-arch-test` suite (git, pinned by commit) and a Sail or
  Spike reference plugin config; none of that is set up yet (`make compliance` is
  still a placeholder).

## 4. RISCOF 1.25.3 — installed 2026-09-05

- PyPI package `riscof`, installed into the project venv:
  ```bash
  $REPO/.venv/bin/pip install riscof==1.25.3
  $REPO/.venv/bin/riscof --version      # "RISC-V Architectural Test Framework., version 1.25.3"
  ```
- Not yet in `requirements.txt` (only cocotb etc. are) — add it when the compliance
  flow lands so a fresh `.venv` gets it (FLOW-006).

## 5. cocotb 2.0.1 / Python 3.13.2 — pre-existing since P0

- `.venv` at the repo root, created from `requirements.txt`. Worktrees symlink it.

## 6. Docker 29.5.2 + LibreLane 3.0.5 (digest-pinned) + sky130A — pre-existing since P0

- See `flow/versions.mk` (`LIBRELANE_IMAGE`, `PDK`, `SCL`). Not touched in B1.

## Open flow items

| id | item |
|---|---|
| FLOW-001 | Spike unpinned (brew bottle of `main`); rebuild from a recorded commit before trusting compliance |
| FLOW-004 | Verible not available in the darwin-arm64 OSS CAD Suite build; decide: separate install or drop from the gate wording |
| FLOW-005 | OSS CAD Suite 2026-07-26 tarball sha256 not recorded |
| FLOW-006 | `riscof` missing from `requirements.txt` |
