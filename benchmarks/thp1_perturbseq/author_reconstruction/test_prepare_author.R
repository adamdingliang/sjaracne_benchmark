#!/usr/bin/env Rscript
# Tiny helper smoke tests. Does not read/download/modify the live THP-1 inputs.
script_argument <- grep("^--file=", commandArgs(trailingOnly = FALSE), value = TRUE)
if (length(script_argument) != 1L) stop("Use Rscript test_prepare_author.R")
here <- dirname(normalizePath(sub("^--file=", "", script_argument), mustWork = TRUE))
source(file.path(here, "prepare_author.R"))
if (!requireNamespace("Matrix", quietly = TRUE)) stop("Matrix required for smoke test")
if (!requireNamespace("scater", quietly = TRUE)) stop("scater required for smoke test")

args <- parse_args(c("--h5ad", "fixture", "--metadata-dir", "fixture", "--resources-dir", "fixture", "--output", "fresh"))
stopifnot(args$gamma == 20, args$n_pc == 10, args$seed == 12345,
          !args$qc_log_counts, args$qc_mad == 3, args$cpm_library == "raw",
          args$min_detected_cells == 2, args$min_perturbed_cells == 20,
          args$self_logfc == -0.1, args$response_logfc == 0.25)
for (bad in list(c("--unknown", "value"), c("--gamma"),
                c("--h5ad", "f", "--metadata-dir", "f", "--resources-dir", "f", "--output", "f", "--chunk-cells", "0"))) {
    stopifnot(inherits(try(parse_args(bad), silent = TRUE), "try-error"))
}
counts <- as(Matrix::Matrix(matrix(c(1, 2, 0, 0, 3, 2), nrow = 3), sparse = TRUE), "dgCMatrix")
original <- counts@x
observed <- as.matrix(log2_cpm(counts, c(3, 5)))
expected <- log2(1 + sweep(as.matrix(counts), 2, c(3, 5), "/") * 1e6)
stopifnot(max(abs(observed - expected)) < 1e-12, identical(counts@x, original))
metric <- c(1, 2, 3, 4, 100)
outliers <- scater::isOutlier(metric, nmads = 3, type = "both", log = FALSE)
stopifnot(identical(as.logical(outliers), c(FALSE, FALSE, FALSE, FALSE, TRUE)))
expected_thresholds <- median(metric) + c(-1, 1) * 3 * mad(metric)
stopifnot(max(abs(as.numeric(attr(outliers, "thresholds")) - expected_thresholds)) < 1e-12)
cat("prepare_author helper smoke tests passed\n")
