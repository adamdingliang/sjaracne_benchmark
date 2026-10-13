#!/usr/bin/env Rscript
# Reproduce the active Fig. 6a metric definitions, not the earlier pilot scores.
# Inputs are reconstructed and explicitly labeled; published values are not fit targets.
argv <- commandArgs(trailingOnly = TRUE)
if (length(argv) != 5L) {
  stop("Usage: score_author.R NETWORK_TSV POSITIVE_REFERENCE_TSV PUBLICATION_DIR OUT_DIR RUN_MANIFEST_JSON")
}
network_file <- argv[1L]
reference_file <- argv[2L]
publication_dir <- argv[3L]
out_dir <- argv[4L]
run_manifest_file <- argv[5L]
if (dir.exists(out_dir)) stop("Refusing to overwrite score output directory")
for (pkg in c("pROC", "jsonlite", "digest")) {
  if (!requireNamespace(pkg, quietly = TRUE)) stop("Missing package: ", pkg)
}
hash <- function(path) digest::digest(file = path, algo = "sha256")
record_path <- function(path) {
  # Native run manifests may be written by Windows Python and scored in WSL.
  if (.Platform$OS.type != "windows" && grepl("^[A-Za-z]:[/\\\\]", path)) {
    path <- gsub("\\\\", "/", path)
    path <- paste0("/mnt/", tolower(substr(path, 1L, 1L)), substring(path, 3L))
  }
  normalizePath(path, mustWork = TRUE)
}
run <- jsonlite::fromJSON(run_manifest_file, simplifyVector = FALSE)
if (!identical(run$status, "complete")) stop("Refusing to score an incomplete native run")
matches <- Filter(function(job) {
  artifact <- job$artifacts[["edges.tsv"]]
  identical(job$status, "complete") && !is.null(artifact) &&
    identical(record_path(artifact$path), normalizePath(network_file, mustWork = TRUE)) &&
    identical(artifact$sha256, hash(network_file))
}, run$consensus)
if (length(matches) != 1L) stop("Network is not a verified completed consensus artifact")
prepare_record <- run$frozen$inputs$prepare_manifest
if (is.null(prepare_record)) stop("Run lacks preparation manifest provenance")
prepare_file <- record_path(prepare_record$path)
if (!identical(hash(prepare_file), prepare_record$sha256)) stop("Preparation manifest hash mismatch")
prepared <- jsonlite::fromJSON(prepare_file, simplifyVector = FALSE)
if (!identical(prepared$status, "complete")) stop("Reference preparation is incomplete")
expected_reference <- prepared$outputs[["reference_positive_edges.tsv"]]$sha256
if (is.null(expected_reference) || !identical(hash(reference_file), expected_reference)) {
  stop("Reference is not the frozen prepared response artifact")
}
publication <- jsonlite::fromJSON(file.path(publication_dir, "manifest.json"))
for (filename in c("tp.tsv", "epr.tsv", "roc_segment.tsv")) {
  if (!identical(hash(file.path(publication_dir, filename)), publication$outputs_sha256[[filename]])) {
    stop("Published source-point hash mismatch: ", filename)
  }
}
source_paths <- c(network = network_file, reference = reference_file,
                  run_manifest = run_manifest_file,
                  prepare_manifest = prepare_file,
                  publication_manifest = file.path(publication_dir, "manifest.json"),
                  publication_tp = file.path(publication_dir, "tp.tsv"),
                  publication_epr = file.path(publication_dir, "epr.tsv"),
                  publication_roc_segment = file.path(publication_dir, "roc_segment.tsv"))
before_hashes <- vapply(source_paths, hash, character(1))
net <- read.delim(network_file, check.names = FALSE, stringsAsFactors = FALSE)
ref <- read.delim(reference_file, check.names = FALSE, stringsAsFactors = FALSE)
if (!all(c("source", "target", "MI") %in% names(net))) stop("Network requires source,target,MI columns")
if (!all(c("source", "target") %in% names(ref))) stop("Reference requires source,target columns")
if (nrow(net) == 0L || any(!is.finite(net$MI)) || any(net$MI < 0)) stop("Invalid network MI")
pair <- function(df) paste(df$source, df$target, sep = "-")
# Preserve the authors' string membership and R sort behavior, including MI ties.
# The full inferred SIG network is NOT restricted to perturbation-eligible sources.
pred <- pair(net)
if (anyDuplicated(pred)) stop("Duplicate/ambiguous hyphen-joined predicted pairs")
if (anyDuplicated(pair(ref))) stop("Duplicate/ambiguous hyphen-joined reference pairs")
ordering <- sort(net$MI, decreasing = TRUE, index.return = TRUE)$ix
net <- net[ordering, , drop = FALSE]
pred <- pred[ordering]
truth <- pred %in% pair(ref)
if (length(unique(truth)) != 2L) stop("Author ROC requires both positive and negative emitted edges")
N <- length(pred)
RNGkind(kind = "Mersenne-Twister", normal.kind = "Inversion", sample.kind = "Rejection")
set.seed(1)
random_order <- sample(seq_len(N), size = N, replace = FALSE)
random_truth <- truth[random_order]
roc_method <- pROC::roc(truth, seq_len(N), direction = ">", quiet = TRUE)
roc_random <- pROC::roc(random_truth, seq_len(N), direction = ">", quiet = TRUE)
ks <- if (N >= 1000L) seq.int(1000L, N, by = 1000L) else integer()
tp <- cumsum(truth)
tp_random <- cumsum(random_truth)
epr <- tp[ks] / tp_random[ks]
epr[!is.finite(epr)] <- NA_real_
curve <- data.frame(k = ks, TP = tp[ks], Random_TP = tp_random[ks], EPR = epr,
                    split_MI_tie = vapply(ks, function(k) k < N && net$MI[k] == net$MI[k+1L], logical(1)))
published_tp <- read.delim(file.path(publication_dir, "tp.tsv"), stringsAsFactors = FALSE)
published_epr <- read.delim(file.path(publication_dir, "epr.tsv"))
published_roc <- read.delim(file.path(publication_dir, "roc_segment.tsv"))
pub <- published_tp[published_tp$method == "scMINER", c("k", "TP")]
names(pub)[2L] <- "published_TP"
comparison <- merge(curve, pub, by = "k", all.x = TRUE)
names(published_epr)[names(published_epr) == "EPR"] <- "published_EPR"
comparison <- merge(comparison, published_epr[, c("k", "published_EPR")], by = "k", all.x = TRUE)
comparison$TP_minus_published <- comparison$TP - comparison$published_TP
comparison$EPR_minus_published <- comparison$EPR - comparison$published_EPR
roc_table <- rbind(
  data.frame(FPR = 1-roc_method$specificities, TPR = roc_method$sensitivities, method = "Reconstructed"),
  data.frame(FPR = 1-roc_random$specificities, TPR = roc_random$sensitivities, method = "Random"))
auc <- as.numeric(pROC::auc(roc_method))
result <- list(
  status = "complete", interpretation = "Reconstructed author-style legacy baseline; not exact prepared-input reproduction",
  reported_edges = N, reference_positive_reported_edges = sum(truth),
  reference_positive_fraction = mean(truth), AUROC = auc,
  Random_AUROC = as.numeric(pROC::auc(roc_random)),
  published_AUROC_rounded = publication$published_AUROC_rounded,
  AUROC_minus_published_rounded = auc-publication$published_AUROC_rounded,
  exact_reproduction_established = FALSE,
  definitions = list(ROC = "pROC on unique ordinal ranks after R MI sorting; direction greater",
                     EPR = "TP_method/TP_R_seed1_shuffle; undefined zero-denominator ratios are NA",
                     reference = "membership against strict-SIG response positives; full inferred SIG pool retained",
                     scope = "No common-candidate-universe substitution; no MI cutoff/labels tuned to published scores"),
  R_version = as.character(getRversion()), RNGkind = RNGkind(), seed = 1L,
  package_versions = lapply(c("pROC", "jsonlite", "digest"), function(p) list(name = p, version = as.character(packageVersion(p)))),
  script_sha256 = hash(sub("^--file=", "", grep("^--file=", commandArgs(), value = TRUE))),
  input_sha256 = as.list(before_hashes), native_run = run)
after_hashes <- vapply(source_paths, hash, character(1))
if (!identical(before_hashes, after_hashes)) stop("Input changed during scoring")
dir.create(out_dir, recursive = TRUE)
write.table(curve, file.path(out_dir, "ranked_curves.tsv"), sep = "\t", row.names = FALSE, quote = FALSE, na = "NA")
write.table(comparison, file.path(out_dir, "comparison_to_publication.tsv"), sep = "\t", row.names = FALSE, quote = FALSE, na = "NA")
write.table(roc_table, file.path(out_dir, "roc_curves.tsv"), sep = "\t", row.names = FALSE, quote = FALSE)
write.table(net, file.path(out_dir, "MI_ranked_edges.tsv"), sep = "\t", row.names = FALSE, quote = FALSE)
# Plot the actual author-style shuffled comparators, not only a theoretical diagonal.
png(file.path(out_dir, "comparison_to_fig6a.png"), width = 2400, height = 800, res = 180)
par(mfrow = c(1,3), mar = c(4.2,4.4,3.2,1))
if (length(ks)) {
  plot(curve$k, curve$TP, type = "l", col = "#2166ac", lwd = 2,
       xlab = "Top-ranked edges (k)", ylab = "Reference-positive edges", main = "TP: reconstruction vs Fig. 6a",
       xlim = range(c(curve$k, pub$k), finite = TRUE),
       ylim = range(c(curve$TP, curve$Random_TP, pub$published_TP), finite = TRUE))
  lines(curve$k, curve$Random_TP, col = "gray50", lwd = 1)
  lines(pub$k, pub$published_TP, col = "#b2182b", lwd = 2)
  legend("topleft", c("Reconstructed", "R-shuffled", "Published"), col = c("#2166ac", "gray50", "#b2182b"), lty = 1, bty = "n", cex = 0.7)
  plot(curve$k, curve$EPR, type = "l", col = "#2166ac", lwd = 2,
       xlab = "Top-ranked edges (k)", ylab = "TP / shuffled TP", main = "EPR: reconstruction vs Fig. 6a",
       xlim = range(c(curve$k, published_epr$k), finite = TRUE),
       ylim = range(c(curve$EPR, published_epr$published_EPR, 1), finite = TRUE))
  lines(published_epr$k, published_epr$published_EPR, col = "#b2182b", lwd = 2)
  abline(h = 1, col = "gray50", lty = 2)
} else {
  plot.new(); title("No 1,000-edge TP point")
  plot.new(); title("No 1,000-edge EPR point")
}
plot(1-roc_method$specificities, roc_method$sensitivities, type = "l", col = "#2166ac", lwd = 2,
     xlim = c(0,1), ylim = c(0,1), xlab = "1-Specificity", ylab = "Sensitivity",
     main = sprintf("ROC: reconstructed AUC %.3f", auc))
lines(1-roc_random$specificities, roc_random$sensitivities, col = "gray50")
lines(published_roc$FPR, published_roc$TPR, col = "#b2182b", lwd = 2)
abline(0,1,lty=2,col="gray75")
title(sub = "Red: published partial segment only; paper AUC ~0.75", cex.sub = 0.65)
dev.off()
output_names <- c("ranked_curves.tsv", "comparison_to_publication.tsv", "roc_curves.tsv",
                  "MI_ranked_edges.tsv", "comparison_to_fig6a.png")
result$output_sha256 <- as.list(setNames(vapply(file.path(out_dir, output_names), hash, character(1)), output_names))
if (!identical(before_hashes, vapply(source_paths, hash, character(1)))) stop("Input changed while writing score outputs")
jsonlite::write_json(result, file.path(out_dir, "metrics.json"), auto_unbox = TRUE, pretty = TRUE, na = "null", digits = 17)
cat(jsonlite::toJSON(result[c("reported_edges", "reference_positive_reported_edges", "AUROC", "Random_AUROC")], auto_unbox = TRUE), "\n")
