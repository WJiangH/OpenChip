# Quality-gate thresholds.
# Iron Rule 5: these are never weakened to make a change pass. Raising them is fine.
# Any exception requires an explicit human-approved waiver in the PR description.

COVERAGE_LINE_MIN   := 90     # % line coverage per module (verilator --coverage)
COVERAGE_TOGGLE_MIN := 90     # % toggle coverage per module

CLOCK_PERIOD_NS := 20         # 50 MHz timing target on $(PDK)
WNS_MIN         := 0          # worst negative slack must be >= 0

FORMAL_BMC_DEPTH := 20        # default BMC depth; per-module .sby may go deeper
