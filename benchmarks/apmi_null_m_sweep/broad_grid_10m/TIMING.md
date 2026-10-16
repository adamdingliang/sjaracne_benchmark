# Broad-grid runtime pilot: October 15, 2026

**Timing only. No full sweep was launched.** The user chose to stop after
runtime measurements and the detailed protocol. No GPDs, calibration models,
smooth parameter functions or inference networks were fitted in this pilot.

## Measured sequential generation

The existing pinned-generator timing helper ran 200,000 draws at each size,
one process at a time, using Npar=40 through WSL Ubuntu:

| m | Draws | Native wall time | Approximate draws/second |
| ---: | ---: | ---: | ---: |
| 2000 | 200000 | 4.16 seconds | 48077 |
| 5000 | 200000 | 10.38 seconds | 19268 |
| 10000 | 200000 | 20.84 seconds | 9597 |

All native exit codes were zero. The helper checked raw lengths, metadata,
finite MI support and hashes. These draws are not production calibration data.
[Original compact sequential records](timing_2026-10-15/sequential/timing_results.json).

## Measured eight-worker capacity (reference)

Eight concurrent workers each generated 100,000 draws at m=10000. Every worker
invoked the same existing helper, with numerical-library thread limits set to
one and forwarded into WSL. The timing-capacity code was committed before
this batch and passed 12 mocked synthetic tests; it caps workers at 12,
draws per worker at 200,000 and m at 10000 so it cannot be used to launch
the proposed 10M production streams.

- Batch elapsed: **19.9653 seconds**, including helper/Python/WSL startup,
  generation and evidence checks.
- Native worker wall times: min **15.64**, median **15.875**, max **16.20 seconds**.
- All eight worker return codes: **0**; no retry or partial result suppression.
- Total parallel timing draws: 800,000. The helper uses the same timing-only
  seed across workers; these are contention replicates, not independent
  scientific streams and must not be reused for model confirmation.

[Frozen capacity request](timing_2026-10-15/parallel8/capacity_request.json)
and [complete capacity results](timing_2026-10-15/parallel8/capacity_results.json)
retain commands, source/executable hashes, start/finish times, per-worker
return codes, native timing/RSS, raw metadata and hashes. Raw payloads are
excluded from this compact copy.

## Measured twelve-worker capacity (requested configuration)

The user subsequently requested **12 workers**, without revoking the instruction
to stop after timing. A second bounded pilot ran twelve concurrent workers,
each with 100,000 draws at m=10000. It did not launch any full calibration.

- Batch elapsed: **21.2264 seconds**, including startup and evidence checks.
- Native worker wall times: min **18.70**, median **18.88**, max **19.20 seconds**.
- All twelve worker return codes: **0**; total timing draws: 1,200,000.
- Aggregate whole-batch throughput: **56,533.37 draws/second**, compared with
  **40,069.60** in the eight-worker pilot: approximately **41.1% higher** in
  this short test. That is not a guarantee of the same improvement over a
  many-hour scientific run. Individual workers slow down under contention;
  the comparison is aggregate completed work, not per-worker speed.

The same timing-only repeated-seed restriction applies. The
[12-worker request](timing_2026-10-15/parallel12/capacity_request.json) and
[12-worker results](timing_2026-10-15/parallel12/capacity_results.json) preserve
the exact records. Earlier eight-worker evidence remains unchanged.

## Projected full-grid cost, not a completion guarantee

For m=50,100,...,10000, sum(m)=1,005,000. At 20M draws per m, the rough
m-weighted generation workload is 20,100,000,000,000 observation-draw units.
Using each sequential pilot's seconds/(draws*m) and averaging those rates
projects to **58.07 single-worker hours** of generation. Dividing by eight
gives an ideal **7.26 hours**, but measured contention makes that idealistic.

The parallel pilot performs 8*100000*10000 = 8,000,000,000 such units:

    workload ratio = 20,100,000,000,000 / 8,000,000,000 = 2512.5
    native-max projection = 2512.5 * 16.20 / 3600 = 11.31 hours
    whole-batch projection = 2512.5 * 19.9653 / 3600 = 13.93 hours

Those are the **eight-worker reference** projections. For the requested twelve
workers, the timing batch performs 12*100000*10000 = 12,000,000,000 units:

    workload ratio = 20,100,000,000,000 / 12,000,000,000 = 1675
    native-max projection = 1675 * 19.20 / 3600 = 8.93 hours
    whole-batch projection = 1675 * 21.2264 / 3600 = 9.88 hours

Thus **roughly 9-10 hours for generation with 12 workers** is the updated
planning estimate, versus roughly 11-14 hours in the eight-worker reference.
Neither range is a confidence interval or guaranteed runtime. Scaling the
whole small-batch time repeats startup overhead that
long streams would amortize; thermal behavior, actual concurrency, other
workloads and the unmeasured long-run schedule can also change throughput.
GPD fitting across threshold candidates, quantile summaries, integrity scans,
validation, smoothing and reporting add work and were not timed here.

The full requested grid would produce 4 billion null pairs and **32 GB
decimal (29.80 GiB)** of raw data. Current resource checks found approximately
93 GiB available RAM and 637 GiB free on D:, with no other native calibration
jobs. Storage is adequate; CPU time is the main cost. These are a resource
snapshot, not reserved capacity or a claim about physical core count.

## Reproduce only these bounded pilots

```powershell
python benchmarks/apmi_null_m_sweep/time_generator.py --generator D:/GitHub/SJARACNe/SJARACNe/bin/apmi_null_generator.exe --out runs/FRESH_DENSE_TIMING --draws 200000 --m 2000 5000 10000
python benchmarks/apmi_null_m_sweep/broad_grid_10m/time_capacity.py --generator D:/GitHub/SJARACNe/SJARACNe/bin/apmi_null_generator.exe --out runs/FRESH_DENSE_CAPACITY8 --workers 8 --draws 100000 --m 10000
python benchmarks/apmi_null_m_sweep/broad_grid_10m/time_capacity.py --generator D:/GitHub/SJARACNe/SJARACNe/bin/apmi_null_generator.exe --out runs/FRESH_DENSE_CAPACITY12 --workers 12 --draws 100000 --m 10000
python -m unittest discover -s benchmarks/apmi_null_m_sweep/broad_grid_10m -p test_time_capacity.py
```

Replace local paths with verified equivalents; output directories must be new
children of ignored runs/. The pinned generator SHA256 is
`08224b6b20e29628be6d89d22eb7e355f8c6a05623e06f801fae5347a70a7f18`.
The full study remains a [prospective protocol](PROTOCOL.md), not an active job.
All pilot raw streams (2.6M draws, 20.8 MB total) remain local under
`runs/apmi_null_dense_timing_20261015/` and
`runs/apmi_null_dense_capacity_20261015/`, plus
`runs/apmi_null_dense_capacity12_20261015/`.
