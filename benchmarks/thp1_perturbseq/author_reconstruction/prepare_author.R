#!/usr/bin/env Rscript
# Author-style reconstruction of THP-1 Figure 6a preparation, not recovery of
# missing upstream RData. Preserve original H5AD; write only to a fresh folder.
# Paper parameters and active downstream author code are pinned in source_pins.

parse_args <- function(args) {
    opts <- list(
        h5ad = NULL, metadata_dir = NULL, resources_dir = NULL, output = NULL,
        qc_mad = "3", qc_log_counts = "FALSE", min_detected_cells = "2",
        min_perturbed_cells = "20", self_logfc = "-0.1", response_logfc = "0.25",
        gamma = "20", n_pc = "10", seed = "12345", chunk_cells = "1024",
        cpm_library = "raw", save_de_rds = "TRUE", allow_version_mismatch = "FALSE"
    )
    if (length(args) == 0L || "--help" %in% args) {
        cat(paste(
            "Usage: Rscript prepare_author.R --h5ad PATH --metadata-dir PATH",
            "       --resources-dir PATH --output FRESH_PATH",
            "Options: --qc-mad 3 --qc-log-counts FALSE --min-detected-cells 2",
            "         --min-perturbed-cells 20 --self-logfc -0.1 --response-logfc 0.25",
            "         --gamma 20 --n-pc 10 --seed 12345 --chunk-cells 1024",
            "         --cpm-library raw|filtered --save-de-rds TRUE",
            "         --allow-version-mismatch FALSE", sep = "\n"), "\n")
        quit(status = 0)
    }
    if (length(args) %% 2L) stop("Every option requires a value")
    for (i in seq(1L, length(args), by = 2L)) {
        if (!startsWith(args[i], "--")) stop("Expected --option: ", args[i])
        key <- gsub("-", "_", substring(args[i], 3L), fixed = TRUE)
        if (!key %in% names(opts)) stop("Unknown option: ", args[i])
        opts[[key]] <- args[i + 1L]
    }
    for (key in c("h5ad", "metadata_dir", "resources_dir", "output")) {
        if (is.null(opts[[key]])) stop("Missing --", gsub("_", "-", key))
    }
    numeric_keys <- c("qc_mad", "min_detected_cells", "min_perturbed_cells", "self_logfc",
                      "response_logfc", "gamma", "n_pc", "seed", "chunk_cells")
    for (key in numeric_keys) {
        opts[[key]] <- suppressWarnings(as.numeric(opts[[key]]))
        if (!is.finite(opts[[key]])) stop("Invalid finite number: ", key)
    }
    for (key in c("qc_log_counts", "save_de_rds", "allow_version_mismatch")) {
        if (!toupper(opts[[key]]) %in% c("TRUE", "FALSE")) stop("Expected TRUE/FALSE: ", key)
        opts[[key]] <- identical(toupper(opts[[key]]), "TRUE")
    }
    for (key in c("min_detected_cells", "min_perturbed_cells", "n_pc", "chunk_cells")) {
        if (opts[[key]] < 1 || opts[[key]] %% 1 != 0) stop("Positive integer required: ", key)
    }
    if (opts$qc_mad < 0 || opts$response_logfc < 0 || opts$gamma <= 0 || opts$seed %% 1 != 0)
        stop("Invalid threshold, gamma, or integer seed")
    if (!opts$cpm_library %in% c("raw", "filtered")) stop("cpm-library must be raw or filtered")
    opts
}

file_sha256 <- function(path) digest::digest(path, algo = "sha256", file = TRUE, serialize = FALSE)
write_json <- function(object, path) {
    if (file.exists(path)) stop("Refusing to overwrite: ", path)
    jsonlite::write_json(object, path, auto_unbox = TRUE, pretty = TRUE, null = "null", digits = 17)
}
write_tsv <- function(object, path) {
    if (file.exists(path)) stop("Refusing to overwrite: ", path)
    write.table(object, path, sep = "\t", quote = FALSE, row.names = FALSE, na = "NA")
}
stamp <- function(...) cat(format(Sys.time(), "%Y-%m-%dT%H:%M:%SZ", tz = "UTC"), ..., "\n")

# H5AD CSR stores cells x genes; HDF5Array reverses it to genes x cells.
# OLD_extract_sparse_array is the exported Bioconductor 3.19/3.20 compatibility
# generic. It extracts an indexed sparse slice, not a dense whole-dataset copy.
read_sparse_counts <- function(counts, gene_indices, cell_indices) {
    sparse <- DelayedArray::OLD_extract_sparse_array(DelayedArray::seed(counts),
                                                     list(gene_indices, cell_indices))
    as(sparse, "dgCMatrix")
}
log2_cpm <- function(counts, library) {
    if (any(!is.finite(library) | library <= 0)) stop("Invalid normalization library")
    counts@x <- log2(1 + counts@x * rep(1e6 / library, diff(counts@p)))
    counts
}

main <- function(opts, script_path) {
    packages <- c("Matrix", "HDF5Array", "DelayedArray", "SingleCellExperiment", "scater",
                  "scran", "scuttle", "jsonlite", "digest", "igraph", "irlba", "RANN", "plyr")
    missing <- packages[!vapply(packages, requireNamespace, logical(1), quietly = TRUE)]
    if (length(missing)) stop("Missing R packages: ", paste(missing, collapse = ", "))
    versions <- setNames(lapply(packages, function(pkg) as.character(utils::packageVersion(pkg))), packages)
    required_versions <- c(scran = "1.32.0", scater = "1.32.1")
    mismatch <- names(required_versions)[vapply(names(required_versions), function(pkg)
        !identical(versions[[pkg]], required_versions[[pkg]]), logical(1))]
    if (length(mismatch) && !opts$allow_version_mismatch)
        stop("Paper-version mismatch: ", paste(mismatch, collapse = ", "),
             "; install scran 1.32.0/scater 1.32.1 or explicitly permit and record mismatch")

    h5ad <- normalizePath(opts$h5ad, mustWork = TRUE)
    metadata_dir <- normalizePath(opts$metadata_dir, mustWork = TRUE)
    resources_dir <- normalizePath(opts$resources_dir, mustWork = TRUE)
    output <- opts$output
    if (file.exists(output)) stop("Output must be fresh; refusing existing path: ", output)
    pins_path <- file.path(dirname(script_path), "source_pins.json")
    pins <- jsonlite::read_json(pins_path, simplifyVector = FALSE)
    resource_records <- lapply(pins$resources, function(resource) {
        path <- file.path(resources_dir, resource$filename)
        if (!file.exists(path) || !identical(file_sha256(path), resource$sha256))
            stop("Pinned resource absent or hash mismatch: ", resource$filename)
        resource
    })
    metadata_manifest_path <- file.path(metadata_dir, "export_metadata_manifest.json")
    meta <- jsonlite::read_json(metadata_manifest_path, simplifyVector = TRUE)
    for (name in c("cells.tsv", "genes.tsv")) {
        if (!identical(file_sha256(file.path(metadata_dir, name)), meta$metadata_files[[name]]$sha256))
            stop("Metadata hash mismatch: ", name)
    }
    stamp("Hashing original H5AD to bind R counts to Python metadata")
    if (!identical(file_sha256(h5ad), meta$h5ad$sha256)) stop("H5AD/metadata source hash mismatch")
    cells <- read.delim(file.path(metadata_dir, "cells.tsv"), check.names = FALSE,
                        stringsAsFactors = FALSE, na.strings = "NA", quote = "")
    genes <- read.delim(file.path(metadata_dir, "genes.tsv"), check.names = FALSE,
                        stringsAsFactors = FALSE, quote = "")
    cells$single_gene_group[is.na(cells$single_gene_group)] <- ""
    if (anyDuplicated(cells$cell_id) || anyDuplicated(genes$gene)) stop("Duplicate cell/gene names")
    if (!identical(as.integer(cells$cell_index), seq_len(nrow(cells)) - 1L) ||
        !identical(as.integer(genes$gene_index), seq_len(nrow(genes)) - 1L)) stop("Shifted metadata indices")
    counts <- HDF5Array::H5SparseMatrix(h5ad, group = "/raw/X")
    if (!identical(as.integer(dim(counts)), c(nrow(genes), nrow(cells))))
        stop("HDF5Array orientation/metadata dimensions do not match")

    annotation_env <- new.env(parent = emptyenv())
    load(file.path(resources_dir, "tf_sigs_hg.RData"), envir = annotation_env)
    if (!exists("tf_sigs", envir = annotation_env, inherits = FALSE)) stop("Annotation has no tf_sigs object")
    annotation <- get("tf_sigs", envir = annotation_env)
    if (!all(c("geneSymbol", "isSIG", "funcType") %in% colnames(annotation))) stop("Unexpected tf_sigs schema")
    is_sig <- tolower(as.character(annotation$isSIG)) %in% c("true", "1")
    full_sig <- unique(as.character(annotation$geneSymbol[is_sig]))
    strict_sig <- unique(as.character(annotation$geneSymbol[as.character(annotation$funcType) == "SIG"]))
    strict_sig <- strict_sig[!is.na(strict_sig) & nzchar(strict_sig)]
    full_sig <- full_sig[!is.na(full_sig) & nzchar(full_sig)]
    supercell_env <- new.env(parent = globalenv())
    for (filename in c("build_knn_graph.R", "supercell_GE.R", "SCimplify.R"))
        sys.source(file.path(resources_dir, filename), envir = supercell_env)

    dir.create(output, recursive = TRUE, showWarnings = FALSE)
    if (!dir.exists(output)) stop("Cannot create output: ", output)
    output <- normalizePath(output, mustWork = TRUE)
    write_json(list(status = "started", time_utc = format(Sys.time(), tz = "UTC"),
                    parameters = opts, h5ad_sha256 = meta$h5ad$sha256), file.path(output, "prepare_started.json"))
    qc_fields <- c("Total_RNA_count", "Total_unique_genes", "Percent_mitochondrial_reads")
    values <- as.matrix(cells[, qc_fields])
    storage.mode(values) <- "double"
    valid <- rowSums(!is.finite(values)) == 0 & values[, 1] > 0 & values[, 2] >= 0 & values[, 3] >= 0
    if (!any(valid)) stop("No cells have valid QC metrics")
    qc_keep <- valid
    qc_thresholds <- list()
    for (i in seq_along(qc_fields)) {
        type <- if (i == 3L) "higher" else "both"
        use_log <- opts$qc_log_counts && i < 3L
        flagged <- scater::isOutlier(values[valid, i], nmads = opts$qc_mad, type = type, log = use_log)
        pass <- valid
        pass[valid] <- !as.logical(flagged)
        cells[[paste0("pass_", qc_fields[i])]] <- pass
        qc_keep <- qc_keep & pass
        qc_thresholds[[qc_fields[i]]] <- list(type = type, log2_metric = use_log,
                                              thresholds = as.numeric(attr(flagged, "thresholds")),
                                              threshold_names = names(attr(flagged, "thresholds")))
    }
    cells$valid_QC_metadata <- valid
    cells$pass_QC <- qc_keep
    retained <- which(qc_keep)
    if (!length(retained)) stop("No cells pass QC")
    detection <- numeric(nrow(genes))
    raw_libraries <- rep(NA_real_, nrow(cells))
    filtered_libraries <- rep(NA_real_, nrow(cells))
    max_library_error <- 0
    max_feature_error <- 0
    stamp("Scanning raw sparse counts for gene detection and QC-library validation")
    for (start in seq(1L, length(retained), by = opts$chunk_cells)) {
        ci <- retained[start:min(length(retained), start + opts$chunk_cells - 1L)]
        block <- read_sparse_counts(counts, NULL, ci)
        if (any(!is.finite(block@x) | block@x < 0 | abs(block@x - round(block@x)) > 1e-8))
            stop("raw.X is not finite nonnegative integer-valued counts")
        library <- Matrix::colSums(block)
        error <- abs(library - cells$Total_RNA_count[ci])
        max_library_error <- max(max_library_error, error)
        if (any(error > 1e-6 + 1e-6 * abs(library))) stop("Raw libraries disagree with Total_RNA_count")
        feature_error <- abs(Matrix::colSums(block > 0) - cells$Total_unique_genes[ci])
        max_feature_error <- max(max_feature_error, feature_error)
        if (any(feature_error > 0)) stop("Raw detected features disagree with Total_unique_genes")
        raw_libraries[ci] <- library
        detection <- detection + Matrix::rowSums(block > 0)
        if (start == 1L || start %% (10L * opts$chunk_cells) == 1L)
            stamp("Count scan", min(length(retained), start + opts$chunk_cells - 1L), "/", length(retained))
    }
    gene_keep <- detection >= opts$min_detected_cells
    gene_indices <- which(gene_keep)
    if (!length(gene_indices)) stop("No genes pass detection filter")
    if (opts$cpm_library == "filtered") {
        for (start in seq(1L, length(retained), by = opts$chunk_cells)) {
            ci <- retained[start:min(length(retained), start + opts$chunk_cells - 1L)]
            filtered_libraries[ci] <- Matrix::colSums(read_sparse_counts(counts, gene_indices, ci))
        }
    }
    library <- if (opts$cpm_library == "raw") raw_libraries else filtered_libraries
    cells$raw_library_validated <- raw_libraries
    cells$CPM_library <- library
    group <- cells$single_gene_group
    nt <- which(qc_keep & group == "non-targeting")
    if (length(nt) < max(2L, opts$n_pc + 1L) || round(length(nt) / opts$gamma) < 2L)
        stop("Too few pure NT cells for requested SuperCell parameters")
    cells$used_for_NT_network <- seq_len(nrow(cells)) %in% nt
    write_tsv(cells, file.path(output, "cell_selection.tsv"))
    symbols <- genes$gene[gene_indices]
    nt_log <- log2_cpm(read_sparse_counts(counts, gene_indices, nt), library[nt])
    dimnames(nt_log) <- list(symbols, cells$cell_id[nt])
    nt_nonzero <- Matrix::rowSums(nt_log > 0) > 0
    nt_mean <- Matrix::rowMeans(nt_log)
    inference_genes <- symbols[nt_nonzero]
    hubs <- inference_genes[inference_genes %in% full_sig]
    if (!length(hubs)) stop("No full-SIG inference hubs have NT expression")
    genes$detected_QC_cells <- detection
    genes$pass_detection_filter <- gene_keep
    genes$has_NT_expression <- genes$gene %in% inference_genes
    genes$isSIG_inference_annotation <- genes$gene %in% full_sig
    genes$strict_SIG_reference_annotation <- genes$gene %in% strict_sig
    genes$used_for_network <- genes$gene %in% inference_genes
    write_tsv(genes, file.path(output, "gene_selection.tsv"))
    stamp("SuperCell on", length(nt), "NT cells; gamma", opts$gamma, "n.pc", opts$n_pc,
          "seed", opts$seed, "all output genes", length(inference_genes))
    set.seed(opts$seed)
    SC <- supercell_env$SCimplify(nt_log, gamma = opts$gamma, n.pc = opts$n_pc, seed = opts$seed)
    MC <- as.matrix(supercell_env$supercell_GE(nt_log, groups = SC$membership))
    if (!identical(dim(MC), c(length(symbols), length(unique(SC$membership))))) stop("Metacell dimensions mismatch")
    rownames(MC) <- symbols
    colnames(MC) <- paste0("MC", seq_len(ncol(MC)))
    inference <- MC[nt_nonzero, , drop = FALSE]
    if (any(!is.finite(inference)) || any(rowSums(inference != 0) == 0)) stop("Invalid inference expression")
    expression <- data.frame(isoformId = rownames(inference), geneSymbol = rownames(inference),
                             inference, check.names = FALSE)
    write_tsv(expression, file.path(output, "expression.exp"))
    writeLines(hubs, file.path(output, "hubs.txt"))
    writeLines(sort(strict_sig), file.path(output, "strict_SIG_genes.txt"))
    membership <- data.frame(cell_id = colnames(nt_log), metacell = as.integer(SC$membership),
                             metacell_name = colnames(MC)[as.integer(SC$membership)])
    write_tsv(membership, file.path(output, "metacell_membership.tsv"))
    saveRDS(list(supercell = SC, log2_CPM_average = MC), file.path(output, "reconstructed_supercells.rds"))
    capture.output(sessionInfo(), file = file.path(output, "sessionInfo.txt"))
    inference_files <- c("expression.exp", "hubs.txt", "metacell_membership.tsv", "gene_selection.tsv", "cell_selection.tsv")
    inference_hashes <- setNames(lapply(inference_files, function(name) list(
        sha256 = file_sha256(file.path(output, name)), size_bytes = file.info(file.path(output, name))$size)), inference_files)
    write_json(list(status = "inference_inputs_ready", scope = "author_style_reconstruction",
                    input_h5ad_sha256 = meta$h5ad$sha256, n_NT_cells = length(nt),
                    n_metacells = ncol(MC), n_genes = nrow(inference), n_hubs = length(hubs),
                    seed = opts$seed, files = inference_hashes,
                    prepare_script_sha256 = file_sha256(script_path), source_pins_sha256 = file_sha256(pins_path)),
               file.path(output, "inference_inputs_ready.json"))
    rm(expression, inference, MC)
    gc(FALSE)

    # The author DE code runs one perturbation-versus-NT findMarkers call per
    # source, with no batch argument or FDR filter. Only strict SIG sources are
    # needed for Figure 6a reference; full isSIG sources remain in inference.
    sizes <- table(group[qc_keep & nzchar(group) & group != "non-targeting"])
    candidates <- sort(intersect(names(sizes), symbols))
    eligible <- data.frame(source = candidates, n_cells = as.integer(sizes[candidates]),
                            strict_SIG = candidates %in% strict_sig,
                            self_logFC = NA_real_, eligible_reference = FALSE,
                            reason = "not_strict_SIG", stringsAsFactors = FALSE)
    de_dir <- file.path(output, "de_results")
    if (opts$save_de_rds) dir.create(de_dir)
    positives_path <- file.path(output, "reference_positive_edges.tsv")
    connection <- file(positives_path, open = "wt")
    on.exit(close(connection), add = TRUE)
    writeLines("source\ttarget\teffect", connection)
    positive_count <- 0L
    positive_self_count <- 0L
    de_filenames <- character()
    for (i in seq_len(nrow(eligible))) {
        source <- eligible$source[i]
        if (!eligible$strict_SIG[i]) next
        if (eligible$n_cells[i] < opts$min_perturbed_cells) {
            eligible$reason[i] <- "fewer_than_min_perturbed_cells"
            next
        }
        kd <- which(qc_keep & group == source)
        kd_log <- log2_cpm(read_sparse_counts(counts, gene_indices, kd), library[kd])
        dimnames(kd_log) <- list(symbols, cells$cell_id[kd])
        # Short precheck uses the same mean-input difference as scran's t-test
        # logFC, but every included source is subsequently verified by scran.
        expected_self <- as.numeric(Matrix::rowMeans(kd_log)[match(source, symbols)] - nt_mean[match(source, symbols)])
        eligible$self_logFC[i] <- expected_self
        if (!is.finite(expected_self) || expected_self >= opts$self_logfc) {
            eligible$reason[i] <- "self_logFC_not_below_cutoff"
            next
        }
        sce <- SingleCellExperiment::SingleCellExperiment(assays = list(logcounts = cbind(nt_log, kd_log)))
        groups <- c(rep("NT", length(nt)), rep(source, length(kd)))
        markers <- scran::findMarkers(sce, groups = groups)
        result <- markers[[source]]
        if (is.null(result) || !"logFC.NT" %in% colnames(result)) stop("Unexpected scran marker schema for ", source)
        effect <- as.numeric(result$logFC.NT)
        names(effect) <- rownames(result)
        observed_self <- effect[source]
        if (length(observed_self) != 1L || !is.finite(observed_self) || abs(observed_self - expected_self) > 1e-8)
            stop("scran/mean-log self effect mismatch for ", source)
        expected <- Matrix::rowMeans(kd_log) - nt_mean
        error <- max(abs(effect[match(symbols, names(effect))] - expected))
        if (!is.finite(error) || error > 1e-8) stop("scran/mean-input effects disagree for ", source)
        eligible$self_logFC[i] <- unname(observed_self)
        eligible$eligible_reference[i] <- observed_self < opts$self_logfc
        eligible$reason[i] <- "eligible"
        positive <- is.finite(effect) & abs(effect) > opts$response_logfc
        rows <- data.frame(source = rep(source, sum(positive)), target = names(effect)[positive],
                           effect = effect[positive], row.names = NULL)
        write.table(rows, connection, sep = "\t", quote = FALSE, row.names = FALSE, col.names = FALSE)
        positive_count <- positive_count + nrow(rows)
        positive_self_count <- positive_self_count + sum(rows$source == rows$target)
        if (opts$save_de_rds) {
            name <- sprintf("%04d.rds", i)
            saveRDS(list(source = source, markers = markers), file.path(de_dir, name))
            de_filenames <- c(de_filenames, name)
        }
        if (i %% 10L == 0L || i == nrow(eligible)) stamp("DE source", i, "/", nrow(eligible), source,
                                                       "reference eligible", sum(eligible$eligible_reference))
        rm(sce, markers, result, kd_log)
    }
    flush(connection)
    close(connection)
    on.exit(NULL, add = FALSE)
    reference_sources <- eligible[eligible$eligible_reference, c("source", "n_cells", "self_logFC"), drop = FALSE]
    if (!nrow(reference_sources)) stop("No strict SIG perturbations meet reference eligibility")
    write_tsv(eligible, file.path(output, "source_eligibility_audit.tsv"))
    write_tsv(reference_sources, file.path(output, "reference_eligible_sources.tsv"))
    if (opts$save_de_rds) write_tsv(data.frame(filename = de_filenames), file.path(output, "de_results_index.tsv"))
    files <- list.files(output, recursive = TRUE, full.names = FALSE)
    file_records <- setNames(lapply(files, function(name) list(
        sha256 = file_sha256(file.path(output, name)), size_bytes = file.info(file.path(output, name))$size)), files)
    manifest <- list(
        schema_version = 1, status = "complete", scope = "author_style_reconstruction_not_exact_recovered_inputs",
        input_h5ad = meta$h5ad, input_h5ad_path_used_by_R = h5ad,
        metadata_manifest_sha256 = file_sha256(metadata_manifest_path),
        prepare_script_sha256 = file_sha256(script_path), source_pins_sha256 = file_sha256(pins_path),
        resources = resource_records, analysis_commit = pins$analysis_commit,
        scminer_commit = pins$scminer_commit, supercell_commit = pins$supercell_commit,
        packages = versions, paper_package_version_mismatches = mismatch, parameters = opts,
        guide_policy = meta$guide_policy, normalization = paste0("log2(1+CPM); ", opts$cpm_library, " gene library denominator"),
        QC = list(nmads = opts$qc_mad, thresholds = qc_thresholds, n_raw_cells = nrow(cells),
                  n_valid_metadata = sum(valid), n_QC_cells = sum(qc_keep), n_NT_cells = length(nt),
                  max_raw_library_vs_metadata_error = max_library_error,
                  max_raw_detected_features_vs_metadata_error = max_feature_error),
        gene_panel = list(n_raw_genes = nrow(genes), n_detection_pass = length(symbols),
                          n_NT_nonzero_inference_genes = length(inference_genes), n_inference_isSIG_hubs = length(hubs),
                          inference_annotation = "isSIG==TRUE; includes combined TF/SIG annotations",
                          reference_annotation = "funcType=='SIG'; excludes combined TF/SIG annotations"),
        supercell = list(version = "1.0 pinned core sources", gamma = opts$gamma, n.pc = opts$n_pc,
                         seed = opts$seed, n.metacells = length(unique(SC$membership)), k.knn = 5,
                         n.var.genes = min(1000, length(symbols)), do.scale = TRUE, fast.pca = TRUE,
                         do.approx = FALSE, clustering = "walktrap", pooling = "all QCed pure NT cells, no replicate split",
                         aggregation = "default supercell_GE: unweighted mean of supplied log2(CPM+1)"),
        reference = list(n_eligible_sources = nrow(reference_sources), n_positive_pairs = positive_count,
                         n_positive_self_pairs = positive_self_count,
                         min_cells = opts$min_perturbed_cells, self_effect_rule = "self_logFC < cutoff",
                         response_rule = "abs(logFC.NT) > cutoff (active author code, not >= text)",
                         no_FDR_filter = TRUE, scran_test = "findMarkers(SCE, groups=groups), package defaults",
                         population = "strict SIG eligible sources; all detection-passing target genes",
                         candidate_universe = "scoring must use the FULL reported SIG prediction list, not just eligible sources",
                         labels_mean = "perturbation response, not proven direct regulatory edges"),
        exact_author_inputs_missing = c("sce_filt_results_proc.Rdata", "filt_targets_results.Rdata",
            "supercells_sce_NT.Rdata", "DE_res_GSM6858449_NT.Rdata", "NT_SIG_net.Rdata", "original expression/hub/consensus files"),
        reconstruction_unknowns = c("Exact author QC log/batch/direction flags and previous filtering unavailable",
            "Original guide collapsing/pure-NT selection code unavailable",
            "CPM denominator before versus after gene filtering unavailable",
            "Exact original SuperCell seed/default overrides and aggregation generator unavailable",
            "Paper-appropriate annotation pin is public, but author's saved annotation object hash unavailable"),
        outputs = file_records, completed_utc = format(Sys.time(), "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")
    )
    write_json(manifest, file.path(output, "prepare_manifest.json"))
    stamp("Preparation complete; reference eligible", nrow(reference_sources), "positives", positive_count)
    invisible(manifest)
}

if (sys.nframe() == 0L) {
    script_argument <- grep("^--file=", commandArgs(trailingOnly = FALSE), value = TRUE)
    if (length(script_argument) != 1L) stop("Run this file with Rscript")
    script_path <- normalizePath(sub("^--file=", "", script_argument), mustWork = TRUE)
    main(parse_args(commandArgs(trailingOnly = TRUE)), script_path)
}
