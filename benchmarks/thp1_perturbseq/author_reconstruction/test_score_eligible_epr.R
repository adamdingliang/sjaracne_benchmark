#!/usr/bin/env Rscript
# Pure-vector tests. Never access or alter benchmark data.
script_file <- sub("^--file=", "", grep("^--file=", commandArgs(), value = TRUE))
source(file.path(dirname(script_file), "score_eligible_epr.R"))
truth <- c(TRUE, FALSE, TRUE, FALSE, TRUE, FALSE)
mi <- c(1, .5, .5, .5, .5, 0)
curve <- eligible_epr_curve(truth, mi, c(1L, 2L, 3L, 6L, 7L))
RNGkind("Mersenne-Twister", "Inversion", "Rejection")
set.seed(1L)
expected_random <- cumsum(sample(truth, length(truth), replace = FALSE))[curve$k]
stopifnot(identical(curve$Random_TP, expected_random), identical(curve$k, c(1L, 2L, 3L, 6L)))
stopifnot(curve$TP_tie_expected[2L] == 1.5, curve$TP_min[2L] == 1, curve$TP_max[2L] == 2)
stopifnot(curve$split_MI_tie[2L], !curve$split_MI_tie[4L])
stopifnot(curve$EPR_R_seed1_shuffle[4L] == 1, curve$Random_TP_expectation[4L] == 3)
stopifnot(isTRUE(all.equal(curve$EPR_R_seed1_shuffle,
                          ifelse(expected_random > 0, curve$TP / expected_random, NA_real_))))
stopifnot(identical(curve, eligible_epr_curve(truth, mi, curve$k)))
all_zero <- eligible_epr_curve(rep(FALSE, 4), rep(1, 4), c(1L, 4L))
stopifnot(all(is.na(all_zero$EPR_R_seed1_shuffle)), all(is.na(all_zero$precision_lift_over_random_expectation)))
expect_error <- function(expression) stopifnot(inherits(try(force(expression), silent = TRUE), "try-error"))
expect_error(eligible_epr_curve(truth, rev(mi), 1L))
expect_error(eligible_epr_curve(truth, mi, 0L))
expect_error(eligible_epr_curve(truth[-1L], mi, 1L))
cat("PASS: deterministic shuffle, EPR, tie bounds, no padding, zero denominators and invalid input tests\n")
