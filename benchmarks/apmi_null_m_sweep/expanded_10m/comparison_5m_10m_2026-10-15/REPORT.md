# Descriptive 5M versus expanded 10M calibration comparison

Descriptive comparison only. The previous package used 5M fitting plus 5M held-out draws per m (base seeds 20261015/20261016); the expanded package used 10M plus 10M draws and fresh base seeds 20261017/20261018. Both simulation count and random streams changed: this is not a matched causal test of simulation-count effects, precision improvement, or why acceptance changed. A status transition is not proof of improvement or regression. Recorded accepted/rejected/failed/incomplete statuses are preserved, never selected by this comparison. No threshold refitting, held-out tuning, empirical fallback, interpolation, biological validation, or biological FDR claim is made. Pointwise confidence is 99.9% under the unchanged per-model family design, not simultaneous coverage across the m grid.

Previous package: 11 exact m sizes. Current package: 19 exact m sizes; 8 are newly run.

Cutoff change is 100 * (current - previous) / previous. Missing diagnostics and zero previous cutoffs have no percentage change. A new size has previous_status=not_run. Rejected GPD cutoffs are diagnostic only, not usable models.

Recorded status transitions (including new sizes):
- accepted -> accepted: 1
- accepted -> rejected: 2
- not_run -> accepted: 3
- not_run -> rejected: 5
- rejected -> accepted: 1
- rejected -> rejected: 7

| m | Previous -> current status | GPD cutoff p=.001, previous -> current (change %) | Actual/nominal p=.001, previous -> current | GPD cutoff p=.0005, previous -> current (change %) | Actual/nominal p=.0005, previous -> current |
|---:|:---|:---|:---|:---|:---|
| 30 | rejected -> rejected | 0.32095401 -> 0.32143852 (0.1509586) | 1.1112 -> 1.0913 | 0.35905606 -> 0.35960065 (0.15167488) | 1.1696 -> 1.1728 |
| 50 | rejected -> rejected | 0.21575008 -> 0.21582216 (0.033407362) | 1.1482 -> 1.1238 | 0.24007331 -> 0.24048948 (0.17335136) | 1.186 -> 1.1286 |
| 80 | rejected -> rejected | 0.14770599 -> 0.14788197 (0.11913827) | 0.972 -> 0.983 | 0.16519964 -> 0.16537692 (0.10731811) | 0.9144 -> 0.9144 |
| 90 | accepted -> rejected | 0.13369017 -> 0.13393484 (0.18300924) | 0.979 -> 0.9617 | 0.14931101 -> 0.14953008 (0.14671799) | 0.9616 -> 0.917 |
| 100 | accepted -> accepted | 0.12129064 -> 0.12175845 (0.38568881) | 1.0018 -> 0.9827 | 0.13522802 -> 0.13587209 (0.47628156) | 1.022 -> 0.9796 |
| 150 | accepted -> rejected | 0.084582055 -> 0.084449637 (-0.1565558) | 0.9648 -> 0.9657 | 0.094841208 -> 0.094563377 (-0.29294332) | 1.0212 -> 1.039 |
| 200 | not_run -> accepted | n/a -> 0.064683276 (n/a) | n/a -> 0.9724 | n/a -> 0.072626464 (n/a) | n/a -> 1.0328 |
| 250 | not_run -> accepted | n/a -> 0.052656045 (n/a) | n/a -> 0.9882 | n/a -> 0.059324928 (n/a) | n/a -> 1.0458 |
| 300 | rejected -> accepted | 0.044291504 -> 0.044334149 (0.096281589) | 1.0208 -> 1.0089 | 0.049954695 -> 0.05011981 (0.33052942) | 1.0804 -> 1.0418 |
| 400 | not_run -> accepted | n/a -> 0.033569637 (n/a) | n/a -> 1.0124 | n/a -> 0.038118261 (n/a) | n/a -> 1.035 |
| 500 | not_run -> rejected | n/a -> 0.027072007 (n/a) | n/a -> 1.0534 | n/a -> 0.030865502 (n/a) | n/a -> 1.0362 |
| 516 | rejected -> rejected | 0.026220958 -> 0.02610761 (-0.43227741) | 1.048 -> 1.0904 | 0.029906299 -> 0.029767873 (-0.4628679) | 1.028 -> 1.083 |
| 600 | not_run -> rejected | n/a -> 0.022558401 (n/a) | n/a -> 1.079 | n/a -> 0.025769113 (n/a) | n/a -> 1.0724 |
| 644 | rejected -> rejected | 0.021076143 -> 0.021051949 (-0.11479141) | 1.123 -> 1.1012 | 0.024097431 -> 0.024097178 (-0.0010494914) | 1.0904 -> 1.0738 |
| 700 | not_run -> rejected | n/a -> 0.019357727 (n/a) | n/a -> 1.1112 | n/a -> 0.022145176 (n/a) | n/a -> 1.1236 |
| 725 | rejected -> rejected | 0.018806798 -> 0.018725091 (-0.43445593) | 1.0612 -> 1.1011 | 0.021628318 -> 0.021452965 (-0.81075804) | 1.02 -> 1.0946 |
| 800 | not_run -> rejected | n/a -> 0.016998285 (n/a) | n/a -> 1.0895 | n/a -> 0.019507815 (n/a) | n/a -> 1.083 |
| 900 | not_run -> rejected | n/a -> 0.015104964 (n/a) | n/a -> 1.1105 | n/a -> 0.017393569 (n/a) | n/a -> 1.087 |
| 1000 | rejected -> rejected | 0.013571395 -> 0.013609614 (0.28161894) | 1.1522 -> 1.1243 | 0.015595653 -> 0.01566143 (0.42176437) | 1.1416 -> 1.1226 |

CSV and JSON retain unrounded values. Both source package checksum manifests were verified. This comparison does not emit or install any model.
