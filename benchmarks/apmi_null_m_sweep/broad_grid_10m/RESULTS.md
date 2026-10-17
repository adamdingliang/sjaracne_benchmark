# Broad-grid empirical-cutoff fitting: completed October 17, 2026

**PCHIP was selected before final validation.** It was more accurate than the
quadratic surface on the tested moderate-probability grid, but the complete
core grid did not satisfy the prespecified simultaneous-interval criterion.
This does not promote a general runtime replacement or change SJARACNe defaults.

The [full report and plots](results_2026-10-17/RESULTS.md) contain every planned
comparison, compact tables, models, hashes and access-history records.
The [process](README.md), [focused-analysis amendment](AMENDMENT_2026-10-17.md)
and original [analysis specification](ANALYSIS_SPEC_2026-10-16.md) describe the
fixed design. This pass compared only empirical quadratic and PCHIP surfaces;
the larger GPD/hybrid/spline candidate analysis remains deferred.

## Design and selection

Use 200 sizes m=50,100,...,10000 with 10M fitting and 10M independent validation
draws each. Construct from 160 sizes' first 8M fitting draws; reserve their last 2M
for internal diagnostics. Select on 20 other sizes and four probabilities
{0.05,0.01,0.001,0.0005}, then refit once on 180 sizes. Twenty interpolation-test
sizes never train the final surfaces. Freeze the primary before final access.

The development selection score was 0.0001292240 for PCHIP versus
0.0004035071 for quadratic; lower is better. Both were evaluated on all
**80 development evaluation cases: 20 sample sizes × four probabilities**.
Each evaluation case is one (m,p) pair in a table, not a biological cell or
an individual sample.

For each case, the fitted curve predicts an MI cutoff. Of n=10 million
development null values, c are at or above that cutoff. The score averages
the squared natural logarithm of ((c+0.5)/(n+1))/p across all 80 cases, with
equal weights. The pseudocount keeps the logarithm finite; reported observed
rates remain c/n. A score of zero means perfect agreement with nominal p;
the score is dimensionless, not a probability or an error percentage.
Only these development cases selected the winner, not final validation.

## Independent final validation

Absolute relative error is abs((observed null exceedance rate / nominal p)-1).
The following rates use the same frozen MI>=cutoff comparator and all planned
evaluation cases, without excluding unfavorable sizes or probabilities.

| Evaluation scope | Method | Observed error within 10% | Median error | Worst error |
| --- | --- | ---: | ---: | ---: |
| 200 sizes × four core p | Quadratic | 797/800 | 0.685% | 28.820% |
| 200 sizes × four core p | PCHIP | 799/800 | 0.449% | 10.069% |
| 200 sizes × 33 fixed p>=0.0005 | Quadratic | 6551/6600 | 0.785% | 32.482% |
| 200 sizes × 33 fixed p>=0.0005 | PCHIP | 6599/6600 | 0.492% | 10.069% |
| 20 untouched test sizes × 33 fixed p>=0.0005 | Quadratic | 656/660 | 0.818% | 12.656% |
| 20 untouched test sizes × 33 fixed p>=0.0005 | PCHIP | 660/660 | 0.542% | 3.540% |

All 49 query probabilities, the exact-m empirical diagnostic and the untouched
legacy-affine comparator are included in the full report. Rare-tail summaries
are not evidence for 10% accuracy at 1e-7: 10M draws yield only one expected event.

## What is and is not confirmed

For the selected PCHIP primary, the 99% Bonferroni study-family intervals over
1600 comparisons classify the 800 core evaluation cases as **784 confirmed, 16 unresolved,
0 inconsistent, 0 invalid**. All 800 had to be confirmed; the study therefore
does **not** confirm the whole proposed core grid. Unresolved is not the same
as a demonstrated accuracy violation, but it is not a pass either.

Of the 16 unresolved core cases, 15 are at p=0.0005, where the simultaneous
intervals extend beyond the 10% band despite observed errors below 10%. The
remaining case is m=50, p=0.05: observed rate 0.0550346, a 10.0692% relative excess.
Its interval also crosses the target-band boundary, rather than lying wholly
outside it. This same case is the sole PCHIP observed-rate miss among the 6600
moderate checks.

The m=50 cutoff is an MI atom: 89,062 validation values equal it exactly.
Changing the cutoff by one upward binary64 step would change its exceedance
count from 550,346 to 461,284. This is a diagnostic of discreteness/comparator
sensitivity, **not** a post-hoc change to the frozen threshold.

The defensible conclusion is that PCHIP is a promising empirical interpolation
candidate with lower observed moderate-grid error than quadratic. This study
does not establish arbitrary off-grid m/p accuracy, a universally 10%-accurate
function, biological false-positive control or new defaults.

## Numerical correction and operational history

The user-approved [roundoff correction](CORRECTION_2026-10-17.md) maps only
MI in [-64 binary64 epsilon,0) to positive zero in analysis copies; raw files
and all positive values are unchanged. All 4000 initial quantile hex values and
both initial-model files were identical before and after normalization.

A subsequent Windows progress-file replacement error interrupted bookkeeping
after all validation/test caches were complete. The [scoring-only continuation](CORRECTION_STATUS_IO_2026-10-17.md)
used the same frozen models and cached data, with no repeated extraction,
selection or refitting. Both failure records are preserved locally. It is the
same evaluation, not a new independent study. The complete test suite passed
175/175 tests before this continuation. An independent read-only audit verified
all 39,200 score rows, all 1600 primary interval calculations/classifications,
all 64 summary records and all 430 continuation input pins.

Raw simulations and caches stay local under ignored `runs/`. The committed
compact evidence contains no raw draws or native network-run artifacts.
