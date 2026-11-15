# Reproducibility package — An FPGA-Based Post-Quantum Security System for UAV Command-and-Control Links

This repository contains the end-to-end link-level emulation used to produce the
system-level evaluation results reported in the paper: the scenario matrix S1–S5
(nominal C2, degraded channel / PER sensitivity, handover–rekey, fault-injection
implicit rejection, security-level scaling) and the compute-vs-transmit bottleneck
analysis.

## Contents

| Path | Description |
|---|---|
| `data/b1_scenarios.json` | Exact scenario dataset used in the paper (parameter sources, S1–S5 results, bottleneck analysis). |
| `emulation/` | Python emulation package: handshake/latency model, aeronautical channel and packet-error model, scenario runner, report and figure generation. |

## How to run

From the repository root:

```bash
python -m emulation
```

This runs S1–S5 plus the bottleneck analysis, prints the report, and regenerates
`output/b1_scenarios.json`. The checked-in dataset under `data/` is the file used
for the numbers in the manuscript.

## Scope note

All results produced by this package are link-level emulation characterizations,
not board-level or flight measurements; the manuscript discusses this boundary
explicitly (GUM-based measurement-uncertainty analysis).

## Reference

H. Yi, “An FPGA-Based Post-Quantum Security System for UAV Command-and-Control Links.”
