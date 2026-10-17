# Final-scoring continuation after Windows status-file failure

The corrected analysis selected PCHIP at2026-10-17 11:04:44 EDT, completed its
180-size refit and froze the primary at11:05:48. All200 validation extraction
tasks completed by11:11:58. During test-size extraction bookkeeping, replacing
the existing progress `status.json` raised Windows `PermissionError`/WinError5.
The controller recorded failure at11:12:25. This was a status-file I/O failure,
not a rejected model, failed raw-data integrity check or unfavorable final
calibration result. The external source of the Windows file lock is unknown.

The failed run, temporary progress file, logs and all completed caches remain
untouched at `runs/apmi_null_broad_fits_20261017_zero_corrected/`. Its final
validation data had been opened for extraction under the frozen final gate.
It would be false to describe the following continuation as preceding all
validation-data access. No final scoring table or final confidence-interval
assessment had been produced. Selection and refitting must not be repeated.

## Allowed continuation

Under the user's existing instruction to continue through final evaluation,
run a separate **final-scoring-only** continuation in a fresh ignored output
directory. It must:

1. Recheck the original corrected request/code pins, selected and frozen
   primary records, both frozen refit models and original final access gate.
2. Verify metadata hashes/roles/source identities for all200 validation caches
   and180 refitting caches. Recover the20 test fitting cache records only if
   every cache is complete and matches its expected49 literal quantiles,
   original raw identity and frozen gate. Missing or inconsistent caches stop
   the continuation; do not overwrite or silently regenerate them.
3. Freeze continuation code/tests, this declaration and all input-record hashes
   in an immutable continuation request **before final scoring**. A prior final
   score table or summary blocks this one-time continuation.
4. Use the already-selected PCHIP primary and both already-refitted surfaces
   without calling any fitting, selection or extraction function. Score the
   existing validation arrays with the unchanged pinned scoring implementation.
5. Preserve the same49 query probabilities,1600-comparison primary correction,
   fixed-domain criteria, exact-m/legacy comparators and numerical-zero policy.
6. Write final artifacts in the fresh directory. Keep copied compact scientific
   locks byte-identical and link the continuation provenance explicitly. Write
   the completion status once, without repeatedly replacing a progress file.

No new draws, model revisions, runner-up substitution, alternative validation
streams, domain narrowing or favorable-count retries are authorized. This is
completion of the same frozen evaluation, not a second confirmatory study.
The SJARACNe engine and defaults remain unchanged.
