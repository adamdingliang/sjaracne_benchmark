#!/usr/bin/env Rscript
# Overlay the paper's named package versions without touching existing environments.
argv <- commandArgs(trailingOnly = TRUE)
if (length(argv) != 2L) stop("Usage: install_paper_packages.R ARCHIVE_DIR WORKSPACE_LIBRARY")
archive_dir <- normalizePath(argv[1L], mustWork = TRUE)
lib <- argv[2L]
dir.create(lib, recursive = TRUE, showWarnings = FALSE)
lib <- normalizePath(lib, mustWork = TRUE)
.libPaths(c(lib, .libPaths()))
versions <- c(scran = "1.32.0", scater = "1.32.1", pROC = "1.18.5")
for (name in names(versions)) {
  archive <- file.path(archive_dir, paste0(name, "_", versions[[name]], ".tar.gz"))
  if (!file.exists(archive)) stop("Missing package archive: ", archive)
  installed <- tryCatch(as.character(utils::packageVersion(name, lib.loc = lib)), error = function(e) NA_character_)
  if (!identical(installed, versions[[name]])) {
    utils::install.packages(archive, repos = NULL, type = "source", lib = lib,
                           INSTALL_opts = c("--no-multiarch", "--no-docs"), Ncpus = 2L)
  }
  actual <- as.character(utils::packageVersion(name, lib.loc = lib))
  if (!identical(actual, versions[[name]])) stop("Package installation did not establish pinned version: ", name)
}
manifest <- list(
  purpose = "Workspace-local paper-version overlay; remaining Bioconductor dependencies recorded, not claimed as fully historical",
  R_version = as.character(getRversion()), library = lib,
  requested_versions = as.list(versions),
  archives_sha256 = lapply(names(versions), function(name) {
    list(name = name, sha256 = digest::digest(file = file.path(archive_dir,
      paste0(name, "_", versions[[name]], ".tar.gz")), algo = "sha256"))
  }),
  dependencies = as.data.frame(installed.packages()[,c("Package", "Version", "LibPath")], stringsAsFactors = FALSE))
jsonlite::write_json(manifest, file.path(lib, "installation_manifest.json"), pretty = TRUE, auto_unbox = TRUE)
cat("Paper-version package overlay installed successfully\n")
