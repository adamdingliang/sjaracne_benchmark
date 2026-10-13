#!/usr/bin/env Rscript
# Realized shuffled-rank EPR in the eligible emitted pool only.
# Preserve all old scorers/results. No inference, response labels or cutoffs change.

eligible_epr_curve <- function(truth, mi, ks, seed = 1L) {
  if (!is.logical(truth) || anyNA(truth) || length(truth) != length(mi) ||
      !length(truth) || any(!is.finite(mi)) || any(mi < 0) || any(diff(mi) > 0)) {
    stop("Invalid eligible truth/MI vectors or MI ordering")
  }
  if (anyNA(ks) || any(ks <= 0) || any(ks != as.integer(ks))) stop("Invalid k")
  N <- length(truth)
  ks <- sort(unique(as.integer(ks[ks <= N])))
  RNGkind("Mersenne-Twister", "Inversion", "Rejection")
  set.seed(seed)
  random_order <- sample(seq_len(N), size = N, replace = FALSE)
  cumulative <- cumsum(truth)
  cumulative_random <- cumsum(truth[random_order])
  groups <- rle(mi)
  ends <- cumsum(groups$lengths)
  starts <- ends - groups$lengths + 1L
  safe_ratio <- function(a, b) ifelse(b > 0, a / b, NA_real_)
  rows <- lapply(ks, function(k) {
    g <- which(ends >= k)[1L]
    before <- starts[g] - 1L
    tp_before <- if (before) cumulative[before] else 0L
    size <- groups$lengths[g]
    p <- cumulative[ends[g]] - tp_before
    take <- k - before
    expected_tp <- tp_before + take * p / size
    random_tp <- cumulative_random[k]
    random_expectation <- k * sum(truth) / N
    data.frame(k = k, TP = cumulative[k], Random_TP = random_tp,
               EPR_R_seed1_shuffle = safe_ratio(cumulative[k], random_tp),
               precision = cumulative[k] / k,
               split_MI_tie = k < N && mi[k] == mi[k + 1L],
               TP_tie_expected = expected_tp,
               TP_min = tp_before + max(0, take - (size - p)),
               TP_max = tp_before + min(take, p),
               EPR_tie_expected_TP_over_same_shuffle = safe_ratio(expected_tp, random_tp),
               Random_TP_expectation = random_expectation,
               precision_lift_over_random_expectation = safe_ratio(expected_tp, random_expectation))
  })
  if (!length(rows)) return(data.frame())
  do.call(rbind, rows)
}

eligible_epr_main <- function(argv) {
  if (length(argv) != 4L) stop("Usage: score_eligible_epr.R THREE_POPULATION_METRICS PREPARED_DIR AUTHOR_COMPARISON_DIR OUT_DIR")
  for (pkg in c("jsonlite", "digest")) {
    if (!requireNamespace(pkg, quietly = TRUE)) stop("Missing package: ", pkg)
  }
  metrics_file <- normalizePath(argv[1L], mustWork = TRUE)
  prepared_dir <- normalizePath(argv[2L], mustWork = TRUE)
  author_dir <- normalizePath(argv[3L], mustWork = TRUE)
  out <- argv[4L]
  if (file.exists(out)) stop("Refusing to overwrite eligible EPR output")
  hash <- function(path) digest::digest(file = path, algo = "sha256")
  record_path <- function(path) {
    if (.Platform$OS.type != "windows" && grepl("^[A-Za-z]:[/\\\\]", path)) {
      path <- gsub("\\\\", "/", path)
      path <- paste0("/mnt/", tolower(substr(path, 1L, 1L)), substring(path, 3L))
    }
    normalizePath(path, mustWork = TRUE)
  }
  prior <- jsonlite::fromJSON(metrics_file, simplifyVector = FALSE)
  if (!identical(prior$status, "complete") || !identical(prior$primary_population, "eligible_emitted")) {
    stop("Require a completed three-population score with eligible emitted primary")
  }
  bound <- list()
  bound[[metrics_file]] <- hash(metrics_file)
  for (path in names(prior$input_sha256)) {
    actual_path <- record_path(path)
    if (!identical(hash(actual_path), prior$input_sha256[[path]])) stop("Frozen input hash mismatch: ", path)
    bound[[actual_path]] <- prior$input_sha256[[path]]
  }
  for (name in names(prior$output_sha256)) {
    path <- normalizePath(file.path(dirname(metrics_file), name), mustWork = TRUE)
    if (!identical(hash(path), prior$output_sha256[[name]])) stop("Saved report hash mismatch")
    bound[[path]] <- prior$output_sha256[[name]]
  }
  require_bound <- function(path) {
    path <- normalizePath(path, mustWork = TRUE)
    if (is.null(bound[[path]])) stop("Requested input is not bound to frozen score: ", path)
    path
  }
  reference_file <- require_bound(file.path(prepared_dir, "reference_positive_edges.tsv"))
  reference <- read.delim(reference_file, check.names = FALSE, stringsAsFactors = FALSE)
  pair <- function(df) paste(df$source, df$target, sep = "\t")
  reference_pairs <- pair(reference)
  if (anyDuplicated(reference_pairs)) stop("Duplicate reference pair")
  eligible_sources <- unlist(prior$universe$sources, use.names = FALSE)
  eligible_targets <- unlist(prior$universe$targets, use.names = FALSE)
  anchors <- as.integer(unlist(prior$top_k_prespecified))
  results <- list()
  all_curves <- list()
  for (name in names(prior$scores)) {
    previous <- prior$scores[[name]]
    network_file <- require_bound(file.path(author_dir, sprintf("score_pc%.0e", previous$consensus_p), "MI_ranked_edges.tsv"))
    net <- read.delim(network_file, check.names = FALSE, stringsAsFactors = FALSE)
    if (nrow(net) != previous$populations$full_emitted$candidate_pairs ||
        anyDuplicated(pair(net)) || any(!is.finite(net$MI)) || any(net$MI < 0) || any(diff(net$MI) > 0)) {
      stop("Saved ranked network differs from frozen score")
    }
    net <- net[net$source %in% eligible_sources & net$target %in% eligible_targets & net$source != net$target, , drop = FALSE]
    truth <- pair(net) %in% reference_pairs
    P <- sum(truth)
    N <- nrow(net)
    expected <- previous$populations$eligible_emitted
    if (N != expected$candidate_pairs || P != expected$reference_positive_pairs_in_population) {
      stop("Eligible N/P differ from frozen score")
    }
    grid <- unique(c(if (N >= 1000L) seq.int(1000L, N, by = 1000L) else integer(), anchors, N))
    curve <- eligible_epr_curve(truth, net$MI, grid, seed = 1L)
    # Check ties and the expectation-based result against the separate Python scorer.
    for (point in expected$top_k) {
      if (!identical(point$status, "complete")) next
      row <- curve[curve$k == point$k, , drop = FALSE]
      if (nrow(row) != 1L || abs(row$TP_tie_expected - point$TP_tie_expected) > 1e-9 ||
          row$TP_min != point$TP_min || row$TP_max != point$TP_max ||
          row$TP < row$TP_min || row$TP > row$TP_max) stop("Tie boundary differs from independent score")
    }
    selected <- lapply(anchors, function(k) {
      if (k > N) return(list(k = k, status = "exceeds_emitted_pairs"))
      c(list(status = "complete"), as.list(curve[curve$k == k, , drop = FALSE]))
    })
    results[[name]] <- list(consensus_p = previous$consensus_p, eligible_emitted_pairs = N,
                           reference_positive_emitted_pairs = P, positive_fraction = P/N,
                           anchors = selected, full_pool_endpoint = as.list(curve[curve$k == N, , drop = FALSE]))
    all_curves[[name]] <- cbind(consensus = name, consensus_p = previous$consensus_p, curve)
  }
  check_inputs <- function() {
    for (path in names(bound)) if (!identical(hash(path), bound[[path]])) stop("Frozen input changed during EPR scoring")
  }
  check_inputs()
  report <- c("# Eligible-source EPR: reconstructed legacy baseline", "",
              "Only eligible-source emitted predictions are ranked and shuffled. The same frozen response labels, inference outputs and consensus alternatives are retained.", "",
              "The random comparator is a uniform permutation without replacement of the same eligible edge pool, using R seed 1 reset separately for each network (Mersenne-Twister, Inversion, Rejection). No new source-target pairs are generated.", "",
              "EPR = integer prefix TP / actual shuffled prefix TP, following the author-style calculation. Saved author MI tie order is preserved. Boundary ties are flagged; the tie-expectation numerator and random-expectation lift are separately reported, not substituted for this EPR.", "",
              "| Consensus p_c | k | TP | Shuffled TP | EPR | Precision | Splits MI tie |",
              "|---:|---:|---:|---:|---:|---:|---|")
  for (result in results) for (row in result$anchors) {
    if (row$status != "complete") {
      report <- c(report, sprintf("| %g | %s | unavailable | unavailable | unavailable | unavailable | unavailable |", result$consensus_p, format(row$k, big.mark = ",", scientific = FALSE)))
    } else {
      report <- c(report, sprintf("| %g | %s | %s | %s | %.4f | %.2f%% | %s |", result$consensus_p,
                                 format(row$k, big.mark = ",", scientific = FALSE), format(row$TP, big.mark = ","),
                                 format(row$Random_TP, big.mark = ","), row$EPR_R_seed1_shuffle,
                                 100*row$precision, if (row$split_MI_tie) "yes" else "no"))
    }
  }
  report <- c(report, "", "These EPRs are conditional enrichment within emitted eligible predictions. Their random baseline is not the earlier full-SIG shuffle. At the complete edge pool EPR is 1 by construction. The result is baseline-only, not evidence of improvement after the sampling change.", "",
              "The entire 1,000-edge trajectory plus full-pool endpoints is saved in ranked_curves.tsv. metrics.json records tied-boundary alternatives, analytic random expectations, R/RNG provenance and SHA256-bound inputs/outputs. Original global scores and the three-population report are unchanged.", "")
  dir.create(out, recursive = TRUE)
  writeLines(report, file.path(out, "REPORT.md"), useBytes = TRUE)
  write.table(do.call(rbind, all_curves), file.path(out, "ranked_curves.tsv"), sep = "\t", row.names = FALSE, quote = FALSE, na = "NA")
  script_file <- sub("^--file=", "", grep("^--file=", commandArgs(), value = TRUE))
  result <- list(status = "complete", scope = "reconstructed_legacy_eligible_emitted_EPR",
                 primary_population = "eligible_emitted", scores = results,
                 definitions = list(EPR = "integer TP / actual eligible-pool R seed-1 shuffled TP",
                                    ties = "preserve saved author tie order for integer TP; tie-expectation numerator separately named",
                                    expectation_lift = "tie-expected TP / (k*P/N), not realized shuffled EPR",
                                    labels = "perturbation responses, not direct-edge ground truth"),
                 R_version = as.character(getRversion()), RNGkind = RNGkind(), seed = 1L,
                 package_versions = lapply(c("jsonlite", "digest"), function(p) list(name = p, version = as.character(packageVersion(p)))),
                 script_sha256 = hash(script_file), input_sha256 = bound,
                 output_sha256 = list(REPORT.md = hash(file.path(out, "REPORT.md")), ranked_curves.tsv = hash(file.path(out, "ranked_curves.tsv"))))
  check_inputs()
  jsonlite::write_json(result, file.path(out, "metrics.json"), auto_unbox = TRUE, pretty = TRUE, digits = 17, na = "null")
  cat(jsonlite::toJSON(list(status = result$status, scores = results), auto_unbox = TRUE, digits = 7), "\n")
}

if (sys.nframe() == 0L) eligible_epr_main(commandArgs(trailingOnly = TRUE))
