#!/usr/bin/env Rscript
# Fresh tiny-fixture diagnostics only: identical calculations, immediate warnings.
argv <- commandArgs(trailingOnly = TRUE)
if (length(argv) != 5L)
    stop("Usage: inspect_smoke_warnings.R PREP_SCRIPT H5AD METADATA_DIR RESOURCES_DIR FRESH_OUTPUT")
options(warn = 1)
script_path <- normalizePath(argv[1L], mustWork = TRUE)
source(script_path)
main(parse_args(c("--h5ad", argv[2L], "--metadata-dir", argv[3L], "--resources-dir", argv[4L],
                  "--output", argv[5L])), script_path)
