# Numerical-zero correction and explicit restart — October 17, 2026

The first focused analysis stopped at2026-10-17 09:50:10 EDT during internal
scoring. Its strict `MI<0` reporting guard conflicted with the generation/data
support tolerance. This is an implementation correction, not a change to model
selection prompted by final calibration results. The user explicitly authorized
treating the tiny negatives as zero and continuing the analysis.

## Exact policy

Let tau=64*binary64 epsilon=1.4210854715202004e-14. For analysis only:

- If -tau <= MI < 0, replace MI with literal positive zero.
- Preserve every positive MI bit, including positive values smaller than tau.
- Reject nonfinite values and MI < -tau. Existing upper-support checks remain.
- Verify the hash of the original input bytes **before** normalization.
- Never overwrite the original generation files or the failed analysis caches.
  Fresh analysis caches contain the normalized values. Record original minimum,
  corrected-negative count, tolerance and policy in their provenance.

Apply the same centralized rule before empirical quantiles, sorting, internal
and development scoring, refitting, validation scoring, zero/tie summaries and
exact-m diagnostics. Zero/unique-count diagnostics describe normalized values;
original negative counts remain separately auditable. All positive-threshold
exceedance counts and positive empirical quantiles are unchanged by this rule.

## Access history and restart boundary

The original failed run is preserved at
`runs/apmi_null_broad_fits_20261017/`, with its request, hashes, initial models,
cache metadata and failure record. All160 training fitting streams and20
development fitting streams had been accessed; both initial surfaces had been
constructed and some internal scoring occurred. No selection was recorded.
No primary, final-access lock, validation cache, final-test fitting cache or
final evaluation exists in that run. It would be false to describe the restart
as occurring before **all** statistical access.

The corrected implementation and tests are frozen in a **fresh** analysis
request before selection, refitting or opening the still-sealed final data.
The new request pins this correction and the failed-run evidence, records the
earlier training/development access, and verifies that no prior final-access
artifacts exist. It re-extracts from exactly the same original raw draws; no new
simulations, replacement seeds or favorable-result retries are introduced.

All other rules in the October16 specification and focused October17 amendment
remain unchanged: two candidates only, the original80-cell development loss,
fixed grids/partitions/domain, one-time180-size refit, no fallback, selected
primary frozen before final access, and the original interval criteria.

Neither the SJARACNe engine nor its runtime defaults are changed. Normalization
is an explicit analysis convention in this corrected benchmark implementation.
