# verif/common — shared DV infrastructure

`wishbone.py` (driver/monitor), `scoreboard.py`, `models/` (golden models,
pure Python, spec-derived — each docstring cites the spec §s it implements).
Shared code is still DV-role territory; RTL agents never touch it.
