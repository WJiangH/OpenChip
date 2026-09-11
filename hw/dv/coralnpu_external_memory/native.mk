# Explicit native imported-IP flow. Intentionally not discovered by make sim.
DV_DIR := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
PYTHON ?= python3
.PHONY: sim controls
sim:
	@test -n "$(RUNTIME)" -a -n "$(SOFTWARE)" -a -n "$(SOFTWARE_REVIEW)" -a -n "$(PROFILE)" -a -n "$(OUTPUT)" -a -n "$(WALL_SECONDS)" || { echo 'Required: RUNTIME SOFTWARE SOFTWARE_REVIEW PROFILE OUTPUT WALL_SECONDS'; exit 2; }
	$(PYTHON) -B "$(DV_DIR)launch.py" --runtime "$(RUNTIME)" --software "$(SOFTWARE)" --software-review "$(SOFTWARE_REVIEW)" --profile "$(PROFILE)" --output "$(OUTPUT)" --wall-seconds "$(WALL_SECONDS)"
controls:
	cd "$(DV_DIR)" && $(PYTHON) -B -m unittest -v test_checker test_exploratory test_cnem31 test_launch
