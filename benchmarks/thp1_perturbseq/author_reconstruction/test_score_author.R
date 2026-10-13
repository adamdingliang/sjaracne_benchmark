#!/usr/bin/env Rscript
# Synthetic integration tests only: no publication workbooks or real data edited.
# Run using the isolated paper R environment after pROC/jsonlite/digest are ready.
script_arg <- grep("^--file=", commandArgs(), value = TRUE)
if (length(script_arg) != 1L) stop("Run this test with Rscript")
script_file <- normalizePath(sub("^--file=", "", script_arg), mustWork = TRUE)
args <- commandArgs(trailingOnly = TRUE)
if (length(args) > 1L) stop("Usage: test_score_author.R [SCORE_AUTHOR_R]")
score_file <- normalizePath(if (length(args)) args[1L] else
                            file.path(dirname(script_file), "score_author.R"), mustWork = TRUE)
for (pkg in c("pROC", "jsonlite", "digest")) {
    if (!requireNamespace(pkg, quietly = TRUE)) stop("Missing package: ", pkg)
}
rscript <- file.path(R.home("bin"), "Rscript")
assert <- function(condition, message) {
    if (!isTRUE(condition)) stop(message, call. = FALSE)
}
sha <- function(path) digest::digest(file = path, algo = "sha256")
write_json <- function(value, path) {
    jsonlite::write_json(value, path, auto_unbox = TRUE, pretty = TRUE,
                         digits = 17, null = "null")
}
write_tsv <- function(value, path) {
    write.table(value, path, sep = "\t", row.names = FALSE, quote = FALSE)
}

make_fixture <- function(root, name) {
    directory <- file.path(root, name)
    dir.create(directory)
    publication <- file.path(directory, "publication")
    dir.create(publication)
    # Full inferred SIG pool includes 1,000 unassayed SOURCE_U edges. Only
    # SOURCE_A supplies response positives. Never filter inference to SOURCE_A.
    net <- data.frame(source = rep(c("SOURCE_U", "SOURCE_A"), each = 1000L),
                      target = sprintf("TARGET%04d", seq_len(2000L)),
                      MI = c(rep(.4, 500L), rep(.2, 500L), rep(.3, 250L),
                             rep(.2, 250L), rep(.1, 500L)))
    ref <- net[1001L:1250L, c("source", "target")]
    network <- file.path(directory, "edges.tsv")
    reference <- file.path(directory, "reference_positive_edges.tsv")
    write_tsv(net, network)
    write_tsv(ref, reference)
    tp <- data.frame(k = rep(c(1000L, 2000L), 2L),
                     TP = c(100L, 200L, 80L, 160L),
                     method = rep(c("scMINER", "Random"), each = 2L),
                     worksheet_row = 3L:6L)
    epr <- data.frame(k = c(1000L, 2000L), EPR = c(1.25, 1.25),
                      worksheet_row = c(3L, 4L))
    roc <- data.frame(FPR = c(1, .8), TPR = c(1, .95),
                      method = "scMINER", worksheet_row = c(3L, 4L))
    write_tsv(tp, file.path(publication, "tp.tsv"))
    write_tsv(epr, file.path(publication, "epr.tsv"))
    write_tsv(roc, file.path(publication, "roc_segment.tsv"))
    pub_names <- c("tp.tsv", "epr.tsv", "roc_segment.tsv")
    pub <- list(published_AUROC_rounded = .75, full_ROC_available = FALSE,
                outputs_sha256 = setNames(lapply(pub_names, function(name)
                    sha(file.path(publication, name))), pub_names))
    write_json(pub, file.path(publication, "manifest.json"))
    prepared <- list(status = "complete",
                     gene_panel = list(n_inference_isSIG_hubs = 2L),
                     reference = list(n_eligible_sources = 1L,
                                      n_positive_pairs = nrow(ref)),
                     outputs = list(reference_positive_edges.tsv =
                         list(sha256 = sha(reference), size_bytes = file.info(reference)$size)))
    prepare_file <- file.path(directory, "prepare_manifest.json")
    write_json(prepared, prepare_file)
    run <- list(status = "complete",
                frozen = list(inputs = list(prepare_manifest =
                    list(path = normalizePath(prepare_file), sha256 = sha(prepare_file)))),
                consensus = list(consensus_pc1e02 = list(status = "complete", p = .01,
                    artifacts = list(edges.tsv = list(path = normalizePath(network),
                        sha256 = sha(network), bytes = file.info(network)$size)))))
    run_file <- file.path(directory, "run_manifest.json")
    write_json(run, run_file)
    list(directory = directory, net = net, ref = ref, network = network,
         reference = reference, publication = publication, prepare_file = prepare_file,
         prepared = prepared, run_file = run_file, run = run,
         out = file.path(directory, "scores"))
}

invoke <- function(fixture) {
    arguments <- c(score_file, fixture$network, fixture$reference,
                   fixture$publication, fixture$out, fixture$run_file)
    output <- suppressWarnings(system2(rscript, args = vapply(arguments, shQuote, character(1)),
                                       stdout = TRUE, stderr = TRUE, timeout = 60))
    code <- attr(output, "status")
    list(status = if (is.null(code)) 0L else code, output = output)
}

expect_failure <- function(fixture, pattern) {
    result <- invoke(fixture)
    assert(result$status != 0L, paste("Expected rejection:", pattern))
    assert(any(grepl(pattern, result$output, fixed = TRUE)),
           paste("Unexpected failure:", paste(result$output, collapse = "\n")))
    assert(!dir.exists(fixture$out), "Rejected inputs left a success output directory")
}

run_suite <- function() {
    root <- tempfile("thp1-score-tests-", tmpdir = tempdir())
    dir.create(root)
    root <- normalizePath(root, mustWork = TRUE)
    # Cleanup only this suite-created, resolved temporary child directory.
    assert(identical(dirname(root), normalizePath(tempdir(), mustWork = TRUE)) &&
           startsWith(basename(root), "thp1-score-tests-"), "Unsafe temporary test directory")
    on.exit(unlink(root, recursive = TRUE), add = TRUE)
    completed <- 0L
    success <- make_fixture(root, "valid")
    input_paths <- c(success$network, success$reference, success$prepare_file, success$run_file,
                     list.files(success$publication, full.names = TRUE))
    input_hashes <- vapply(input_paths, sha, character(1))
    result <- invoke(success)
    assert(result$status == 0L, paste(result$output, collapse = "\n"))
    metrics <- jsonlite::fromJSON(file.path(success$out, "metrics.json"))
    ranked <- read.delim(file.path(success$out, "MI_ranked_edges.tsv"))
    curve <- read.delim(file.path(success$out, "ranked_curves.tsv"))
    assert(metrics$reported_edges == 2000L, "Full inferred SIG pool was restricted")
    assert(sum(ranked$source == "SOURCE_U") == 1000L, "Unassayed source edges were filtered")
    assert(metrics$reference_positive_reported_edges == 250L, "Wrong positive membership")
    # Exactly 500 of 1,750 negatives precede every positive. AUC = 1-500/1750.
    assert(abs(metrics$AUROC - 5/7) < 1e-8, "Ordinal ROC differs from analytic AUC")
    # All equal-MI .2 negatives keep their original consensus order.
    tied <- ranked$target[ranked$MI == .2]
    assert(identical(tied, success$net$target[success$net$MI == .2]), "MI tie order changed")
    assert(all(diff(ranked$MI) <= 0), "MI order is not decreasing")
    assert(identical(as.integer(curve$k), c(1000L, 2000L)), "Wrong author top-k grid")
    assert(identical(as.integer(curve$TP), c(250L, 250L)), "Wrong cumulative TP")
    assert(identical(curve$split_MI_tie, c(TRUE, FALSE)), "Tie-boundary flag incorrect")
    # Independent base-R shuffle of the same ordinal population.
    truth <- ranked$source == "SOURCE_A" & ranked$target %in% success$ref$target
    RNGkind("Mersenne-Twister", "Inversion", "Rejection")
    set.seed(1)
    shuffled <- sample(truth, length(truth), replace = FALSE)
    expected_random_tp <- cumsum(shuffled)[c(1000L, 2000L)]
    assert(identical(as.integer(curve$Random_TP), as.integer(expected_random_tp)),
           "Shuffled TP differs from the author's R seed-1 convention")
    assert(max(abs(curve$EPR - curve$TP / expected_random_tp)) < 1e-8,
           "EPR does not use actual shuffled TP")
    # Pairwise ordinal AUC, independently of pROC and the scorer's ROC call.
    positive_ranks <- which(shuffled)
    negative_ranks <- which(!shuffled)
    random_auc <- sum(vapply(positive_ranks, function(rank)
        sum(negative_ranks > rank), integer(1))) / (length(positive_ranks)*length(negative_ranks))
    assert(abs(metrics$Random_AUROC - random_auc) < 1e-8, "Random ordinal AUC mismatch")
    assert(identical(metrics$exact_reproduction_established, FALSE), "Synthetic run claimed exact paper reproduction")
    assert(identical(vapply(input_paths, sha, character(1)), input_hashes), "Scoring modified frozen inputs")
    completed <- completed + 1L

    for (name in c("network", "reference", "publication_tp", "publication_epr", "publication_roc")) {
        item <- make_fixture(root, paste0("tamper_", name))
        path <- switch(name, network = item$network, reference = item$reference,
                       publication_tp = file.path(item$publication, "tp.tsv"),
                       publication_epr = file.path(item$publication, "epr.tsv"),
                       publication_roc = file.path(item$publication, "roc_segment.tsv"))
        cat("\n", file = path, append = TRUE)
        pattern <- switch(name, network = "verified completed consensus artifact",
                          reference = "frozen prepared response artifact", "Published source-point hash mismatch")
        expect_failure(item, pattern)
        completed <- completed + 1L
    }
    item <- make_fixture(root, "tamper_prepare_manifest")
    cat("\n", file = item$prepare_file, append = TRUE)
    expect_failure(item, "Preparation manifest hash mismatch")
    completed <- completed + 1L

    item <- make_fixture(root, "incomplete_run")
    item$run$status <- "failed"
    write_json(item$run, item$run_file)
    expect_failure(item, "incomplete native run")
    completed <- completed + 1L

    item <- make_fixture(root, "incomplete_prepare")
    item$prepared$status <- "started"
    write_json(item$prepared, item$prepare_file)
    item$run$frozen$inputs$prepare_manifest$sha256 <- sha(item$prepare_file)
    write_json(item$run, item$run_file)
    expect_failure(item, "Reference preparation is incomplete")
    completed <- completed + 1L

    item <- make_fixture(root, "ambiguous_consensus_artifact")
    item$run$consensus$second_job <- item$run$consensus[[1L]]
    write_json(item$run, item$run_file)
    expect_failure(item, "verified completed consensus artifact")
    completed <- completed + 1L

    item <- make_fixture(root, "no_prepare_provenance")
    item$run$frozen$inputs$prepare_manifest <- NULL
    write_json(item$run, item$run_file)
    expect_failure(item, "Run lacks preparation manifest provenance")
    completed <- completed + 1L

    item <- make_fixture(root, "no_overwrite")
    dir.create(item$out)
    marker <- file.path(item$out, "must_remain.txt")
    writeLines("pre-existing test output must remain", marker)
    marker_hash <- sha(marker)
    result <- invoke(item)
    assert(result$status != 0L && any(grepl("Refusing to overwrite", result$output, fixed = TRUE)),
           "Existing output was not rejected")
    assert(identical(sha(marker), marker_hash), "Existing output was modified")
    assert(identical(list.files(item$out), "must_remain.txt"), "Rejected overwrite created extra output")
    completed <- completed + 1L
    cat("PASS:", completed, "synthetic author-scoring integration cases\n")
}

run_suite()
