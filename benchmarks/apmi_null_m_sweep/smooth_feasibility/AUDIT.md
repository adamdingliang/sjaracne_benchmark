# Independent read-only audit

The audit used separate numerical calculations rather than trusting the
runner's scoring or smoothing functions. No discrepancy was found.

- Verified all 38 original raw SHA256 hashes and 38 sorted-cache hashes and
  ascending orderings.
- Checked all 304 empirical quantile indices, 2,432 prediction/training-size
  records, 4,864 count/rate/tie/interval rows and 32 summary groups.
- Reproduced 1,558 mathematically evaluable smooth predictions with separate
  polynomial, PCHIP and GPD calculations (agreement within 3e-12).
- Recounted predictions directly on original unsorted streams at m=50 and
  m=725, for both fitting and validation streams.
- Checked frozen code/request/output hashes, leave-entire-m-out exclusions,
  probability probe separation, report numbers and figure readability.
- Confirmed that in-sample exact-m baseline fitting rows have no binomial
  interval; their validation rows retain descriptive pointwise intervals.

The new workflow has 45 passing synthetic checks, including three packaging
checks added after execution; the execution snapshot retains the 42 checks
present before the real analysis. Existing expanded-sweep, original-sweep and
capacity groups also passed: 54, 32 and 12 tests respectively, 143 total with
the new checks. Tests do not simulate scientific nulls or launch inference.

## Post-hoc probability-axis decomposition

This diagnostic was performed after reviewing the fixed candidate results.
It does not alter any candidate, predeclared summary, gate or supported domain.

Remove m-axis interpolation entirely: take each size's own fitting quantiles
at the existing eight p knots, apply the same PCHIP interpolation in log(p)
and log(cutoff), and count validation MI >= that predicted cutoff.

| m | p | Cutoff interpolated from exact-m p knots | Validation actual/nominal |
| ---: | ---: | ---: | ---: |
| 50 | 0.02 | 0.10613124172690798 | 1.60291 |
| 50 | 0.005 | 0.1639813592206255 | 1.05744 |
| 725 | 0.005 | 0.012132857597074859 | 1.23974 |
| 900 | 0.005 | 0.00977403202487248 | 1.23482 |

Thus p-axis interpolation alone reproduces large errors at several problematic
points. This does not establish the explanation for every error or imply that
denser knots will automatically meet the target. It does support examining
p-axis representation before generating a large new m grid.

To reproduce from the local sorted copies (no new fit or generation):

```python
import json
from pathlib import Path
import numpy as np
from scipy.interpolate import PchipInterpolator

run = Path('runs/apmi_null_smooth_feasibility_20261015')
request = json.loads((run / 'request.json').read_text())
items = json.loads((run / 'extraction.json').read_text())
for m, p in [(50, .02), (50, .005), (725, .005), (900, .005)]:
    item = next(row for row in items if row['m'] == m)
    quantiles = {row['nominal_p']: row['cutoff'] for row in item['quantiles']}
    knots = np.sort(request['knot_p'])
    cutoffs = np.array([quantiles[q] for q in knots])
    threshold = np.exp(PchipInterpolator(np.log(knots), np.log(cutoffs))(np.log(p)))
    values = np.load(item['sorted_cache']['validation']['path'], mmap_mode='r')
    count = len(values) - np.searchsorted(values, threshold, side='left')
    print(m, p, float(threshold), count / len(values) / p)
```

Source/cache byte hashes are in the frozen
[extraction record](results_2026-10-15/extraction.json). These previously inspected
validation data remain exploratory, not fresh confirmation.
