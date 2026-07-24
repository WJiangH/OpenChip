# pd/ — LibreLane physical design. Owned by the backend-engineer role.

Per top: `pd/<top>/config.yaml`, pin order file, and SIGNOFF.md (committed
summary: utilization, Fmax, WNS/TNS, DRC/LVS, tool versions). `runs/` output is
gitignored — numbers get committed, gigabytes don't. Signoff bar: DRC = 0,
LVS clean, WNS ≥ 0 at 50 MHz, and GL-sim re-passes the M3 firmware.
Run: `make gds MOD=<top>` (Docker required).
