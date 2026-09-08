# OpenChip

OpenChip is an open framework for developing silicon with collaborating agents.
It gives architecture, RTL, verification, software and physical design separate
owners, connects their work through reviewed contracts, and binds acceptance to
reproducible evidence.

An orchestrator manages the agreed goal and dependencies. Specialists own their
work from implementation through a manifest pull request; independent reviewers
check behavior, evidence and scope before authorized integration. The canonical
methods in [`.agents/skills/`](.agents/skills/) work across coding-agent clients.
Start with the [agent constitution](AGENTS.md).

## What works today

The reference `blink` and tinyNPU designs exercise lint, cocotb simulation and
selected formal jobs. Public CI also checks framework tooling and role boundaries,
and packages the exact tested source after successful main-branch runs.
[Verification](docs/VERIFICATION.md) records the tested scope, coverage denominators
and remaining gaps. These results establish neither full-SoC closure nor tapeout
readiness. Coverage reporting is diagnostic; lifecycle signoff is a manual,
independently reviewed process.

The GitHub agent workflow supports its configured provider's dispatch and review.
Methods and local durable state support session resumption; they do not implement
a cross-provider scheduler, enforced workspace isolation or background monitoring.

## Run the framework and reference checks

```bash
make framework-test           # Python, documentation and boundary checks
make agents                   # inspect available coding-agent clients
make agents-sync              # expose canonical skills to supported clients
make lint                     # reference RTL lint
make sim MOD=npu              # tinyNPU cocotb regression
make formal MOD=blink         # configured reference formal jobs
make help                     # other entrypoints, including unimplemented targets
```

Framework checks need Python 3.9+ and shell/Git tools. Reference hardware checks
need the pinned EDA tools and Python dependencies described in
[CI and toolchain](docs/CI_CD.md). Imported IP may retain its native build,
verification and implementation tools.

## Direction and documentation

The next engineering direction is to evaluate and adapt upstream CoralNPU,
starting with a pinned, reproducible upstream baseline and a workload acceptance
contract. This integration has not been executed here. The current tinyNPU stays
a fast framework regression. See the [roadmap](docs/ROADMAP.md).

- [Constitution and ownership](AGENTS.md): startup, independent roles and branch delivery.
- [Silicon lifecycle](docs/SILICON_LIFECYCLE.md): incremental, scoped signoff from feasibility through production validation.
- [Verification](docs/VERIFICATION.md): methods, public assets, recorded results and coverage diagnostics.
- [CI and toolchain](docs/CI_CD.md): actual jobs, pins and tested-source artifacts.
- [Attribution](docs/AGENT_ATTRIBUTION.md): registered identities and evidence limits.
- [Specifications](docs/spec/README.md) and [architecture decisions](docs/adr/): specialist-owned engineering contracts.

Project goals, dispatch state and private chip evidence belong in an approved
local store. Reusable [state](docs/templates/ORCHESTRATION_STATE.md) and
[signoff](docs/templates/SIGNOFF_RECORD.md) templates contain no project data.

Licensed under [Apache-2.0](LICENSE).
