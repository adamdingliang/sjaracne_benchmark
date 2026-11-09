#!/usr/bin/env Rscript
# Compute NetBID2 topology QC on saved final DREAM networks, without inference,
# accuracy rescoring, raw-MI reads, hash scans, or HTML generation.
# Usage: Rscript --vanilla compute_dream_topology.R REPORT_DIR OUTPUT_DIR
# Optional independent bulk check: append BULK_GRAPH BULK_NETWORK_SUMMARY_TSV.
# REPORT_DIR contains dream_rows.json and dream_provenance.json. Local saved
# graphs and requested-hub lists must be available at the recorded paths.
# Windows paths in those manifests are mapped to /mnt/<drive>/ under WSL.
suppressPackageStartupMessages(library(NetBID2))
for (package in c("jsonlite", "digest")) {
  if (!requireNamespace(package, quietly = TRUE)) stop("Missing installed package: ", package)
}
args <- commandArgs(trailingOnly = TRUE)
if (!length(args) %in% c(2L, 4L)) stop("Expected REPORT_DIR OUTPUT_DIR [BULK_GRAPH BULK_SUMMARY_TSV]")
report_dir <- normalizePath(args[[1]], mustWork = TRUE)
output_dir <- args[[2]]
if (!dir.exists(output_dir)) dir.create(output_dir, recursive = TRUE)
rows <- jsonlite::read_json(file.path(report_dir, "dream_rows.json"), simplifyVector = FALSE)$rows
executions <- jsonlite::read_json(file.path(report_dir, "dream_provenance.json"), simplifyVector = FALSE)$executions
execution_ids <- vapply(executions, `[[`, character(1), "row_id")
if (anyDuplicated(execution_ids)) stop("Duplicate execution row IDs")
local_path <- function(path) {
  path <- gsub("\\", "/", path, fixed = TRUE)
  if (.Platform$OS.type == "unix" && grepl("^[A-Za-z]:/", path)) {
    path <- paste0("/mnt/", tolower(substr(path, 1L, 1L)), substr(path, 3L, nchar(path)))
  }
  normalizePath(path, mustWork = TRUE)
}
read_graph <- function(path) {
  # Preserve directed edges, loops, parallel edges and incident endpoints. A
  # zero-target source row adds no graph vertex, exactly as in bulk edge lists.
  if (grepl("\\.adj$", path, ignore.case = TRUE)) {
    lines <- readLines(path, warn = FALSE)
    lines <- lines[nzchar(lines) & !startsWith(lines, ">")]
    fields <- strsplit(lines, "\t", fixed = TRUE)
    if (any(lengths(fields) %% 2L != 1L)) stop("Invalid adjacency row in ", path)
    sources <- vapply(fields, `[[`, character(1), 1L)
    if (anyDuplicated(sources)) stop("Duplicate source rows in ", path)
    edge_tables <- lapply(fields, function(x) {
      if (length(x) == 1L) return(NULL)
      index <- seq.int(2L, length(x), by = 2L)
      data.frame(source = rep(x[[1L]], length(index)), target = x[index], MI = as.numeric(x[index + 1L]), stringsAsFactors = FALSE)
    })
    edge_table <- do.call(rbind, edge_tables)
    if (is.null(edge_table)) edge_table <- data.frame(source = character(), target = character(), MI = numeric())
    if (any(!is.finite(edge_table$MI))) stop("Nonfinite MI in ", path)
    temporary <- tempfile(fileext = ".tsv")
    on.exit(unlink(temporary), add = TRUE)
    write.table(edge_table, temporary, sep = "\t", quote = FALSE, row.names = FALSE)
    network <- get.SJAracne.network(temporary)
  } else {
    network <- get.SJAracne.network(path)
  }
  if (!is.list(network) || !inherits(network$igraph_obj, "igraph")) stop("Invalid NetBID2 graph object")
  if (igraph::ecount(network$igraph_obj) != nrow(network$network_dat)) stop("NetBID2 edge count mismatch")
  network$igraph_obj
}
fit_r2 <- function(graph) {
  # Exact NetBID2::check_scalefree fitting definition, with bulk wrapper guards.
  # Use all incident vertices and total degree, not requested hub out-degree.
  adjusted_r2 <- NA_real_
  reason <- ""
  maximum <- NA_integer_
  if (igraph::vcount(graph) > 0L) {
    maximum <- max(igraph::degree(graph))
    if (maximum >= 3L) {
      distribution <- igraph::degree_distribution(graph)
      fit_data <- data.frame(k = seq_len(maximum), pk = distribution[-1L] + 1 / igraph::vcount(graph))
      model <- stats::lm(log10(pk) ~ log10(k), data = fit_data)
      candidate <- summary(model)$adj.r.squared
      if (is.finite(candidate)) adjusted_r2 <- candidate else reason <- "nonfinite adjusted R2"
    } else reason <- "maximum total degree below 3"
  } else reason <- "no incident graph vertices"
  list(adjusted_r2 = adjusted_r2, undefined_reason = reason, max_degree = maximum)
}
qc <- vector("list", length(rows))
for (i in seq_along(rows)) {
  row <- rows[[i]]
  execution_index <- match(row$row_id, execution_ids)
  if (is.na(execution_index)) stop("No execution provenance for ", row$row_id)
  execution <- executions[[execution_index]]
  graph <- read_graph(local_path(execution$local_network))
  drivers <- trimws(readLines(local_path(execution$local_input_paths$hubs), warn = FALSE))
  drivers <- drivers[nzchar(drivers)]
  if (!length(drivers) || anyDuplicated(drivers)) stop("Empty or duplicate driver list")
  out_degree <- igraph::degree(graph, mode = "out")
  driver_degree <- stats::setNames(rep.int(0L, length(drivers)), drivers)
  shared <- intersect(names(out_degree), drivers)
  driver_degree[shared] <- as.integer(out_degree[shared])
  active <- driver_degree[driver_degree > 0L]
  stopifnot(igraph::ecount(graph) == row$edges, length(drivers) == row$requested_hubs,
            length(active) == row$active_hubs, stats::median(driver_degree) == row$median_targets)
  fit <- fit_r2(graph)
  qc[[i]] <- data.frame(row_id = row$row_id, dataset = row$dataset,
    method = execution$historical_method_key, edges = igraph::ecount(graph),
    active_hubs = length(active), requested_hubs = length(drivers),
    median_targets = stats::median(driver_degree),
    median_targets_active = if (length(active)) stats::median(active) else NA_real_,
    incident_nodes = igraph::vcount(graph), max_total_degree = fit$max_degree,
    fit_integer_degree_bins = if (is.finite(fit$max_degree) && fit$max_degree >= 3L) fit$max_degree else 0L,
    adjusted_scale_free_r2 = fit$adjusted_r2, undefined_reason = fit$undefined_reason,
    self_loops = sum(igraph::which_loop(graph)), parallel_edges = sum(igraph::which_multiple(graph)),
    counts_match_frozen = TRUE, stringsAsFactors = FALSE)
  cat(sprintf("QC %d/%d %s %s R2=%s\n", i, length(rows), row$dataset,
              execution$historical_method_key, format(fit$adjusted_r2, digits = 9)))
}
qc <- do.call(rbind, qc)
bulk_check <- NULL
if (length(args) == 4L) {
  graph <- read_graph(local_path(args[[3]]))
  calculated <- fit_r2(graph)$adjusted_r2
  grDevices::pdf(file = NULL)
  installed <- get("check_scalefree", asNamespace("NetBID2"))(graph)
  grDevices::dev.off()
  frozen <- read.delim(local_path(args[[4]]), stringsAsFactors = FALSE)
  expected <- frozen$value[frozen$metric == "scale_free_adjusted_r2"]
  stopifnot(length(expected) == 1L, identical(calculated, installed), abs(calculated - expected) < 1e-14)
  bulk_check <- list(graph = args[[3]], frozen_summary = args[[4]],
    graph_bytes = file.info(local_path(args[[3]]))$size, edges = igraph::ecount(graph),
    incident_nodes = igraph::vcount(graph), recomputed_r2 = calculated,
    installed_NetBID2_check_scalefree_r2 = installed, frozen_r2 = expected,
    formula_and_package_identical = TRUE, frozen_difference = calculated - expected, passed = TRUE)
}
write.table(qc, file.path(output_dir, "dream_topology.tsv"), sep = "\t", row.names = FALSE, quote = FALSE, na = "NA")
script_argument <- grep("^--file=", commandArgs(trailingOnly = FALSE), value = TRUE)
script_path <- sub("^--file=", "", script_argument[[1L]])
provenance <- list(schema = "sjaracne-final-netbid2-topology-v1",
  created_utc = format(Sys.time(), "%Y-%m-%dT%H:%M:%SZ", tz = "UTC"),
  script = "compute_dream_topology.R", script_sha256 = digest::digest(file = script_path, algo = "sha256"),
  activity = "Saved final graph QC only; no inference, accuracy rescoring, raw-MI reads, or raw hash scan",
  inputs = c("dream_rows.json", "dream_provenance.json"),
  local_inputs = "Saved final graphs and requested hubs are resolved from dream_provenance.json; they are not redistributed in this report",
  environment = list(R = R.version.string, NetBID2 = as.character(packageVersion("NetBID2")),
    NetBID2_RemoteSha = packageDescription("NetBID2")$RemoteSha, igraph = as.character(packageVersion("igraph"))),
  method = list(package_reference = "NetBID2::check_scalefree",
    reference_bulk_script = "D:/GitHub/local_runs/SIG_sequential_HDD_optional_hashes_20261109/scripts/run_netbid_qc.R",
    graph_reader = "NetBID2::get.SJAracne.network; directed graph from source and target columns; no simplification",
    degree_population = "All incident vertices, total degree (in plus out); requested zero-target hubs are not added as isolates",
    formula = "lm(log10(pk) ~ log10(k)) with intercept; pk=degree_distribution[-1]+1/V; k=1..max(total degree); adjusted R2",
    zero_bins = "Zero-degree bin excluded; unobserved positive integer degree bins receive 1/V",
    undefined = "NA for empty graph, maximum total degree below 3, or nonfinite adjusted R2; finite negative values retained",
    median_targets = "All requested hubs including zero-target hubs",
    adjacency_normalization = "Expand each noncomment source row to directed source-target-MI edges; omit zero-target rows from edge graph only; temporary files removed",
    validation = "Edges, active hubs, requested hubs and median targets equal all frozen source records"),
  row_count = nrow(qc), undefined_fit_count = sum(is.na(qc$adjusted_scale_free_r2)),
  all_counts_match_frozen = all(qc$counts_match_frozen),
  independent_bulk_crosscheck = bulk_check,
  installed_check_scalefree_source = deparse(get("check_scalefree", asNamespace("NetBID2"))))
jsonlite::write_json(provenance, file.path(output_dir, "topology_provenance.json"), pretty = TRUE,
                     auto_unbox = TRUE, na = "null", digits = 17)
cat("COMPLETE", nrow(qc), "rows; undefined fits", provenance$undefined_fit_count, "\n")