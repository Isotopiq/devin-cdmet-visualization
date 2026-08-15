suppressPackageStartupMessages({
  library(pheatmap)
  library(jsonlite)
  library(grid)
})

script_dir <- dirname(sub("^--file=", "", commandArgs(trailingOnly = FALSE)[grep("^--file=", commandArgs(trailingOnly = FALSE))]))
source(file.path(script_dir, "theme_publication.R"))

args <- commandArgs(trailingOnly = TRUE)
input_file <- args[1]
output_dir <- args[2]

payload <- fromJSON(input_file, simplifyDataFrame = FALSE)

# robust matrix conversion from jsonlite output
to_matrix <- function(m, n_cols) {
  if (is.matrix(m)) {
    return(m)
  }
  if (is.data.frame(m)) {
    return(as.matrix(m))
  }
  if (is.list(m)) {
    rows <- lapply(m, function(row) {
      v <- rep(NA_real_, n_cols)
      if (is.null(row)) return(v)
      if (is.list(row)) {
        for (j in seq_len(min(n_cols, length(row)))) {
          el <- row[[j]]
          if (!is.null(el)) {
            num <- suppressWarnings(as.numeric(el))
            if (!is.na(num)) v[j] <- num
          }
        }
      } else {
        raw <- unlist(row)
        l <- min(n_cols, length(raw))
        if (l > 0) {
          nums <- suppressWarnings(as.numeric(raw[seq_len(l)]))
          not_na <- !is.na(nums)
          v[seq_len(l)][not_na] <- nums[not_na]
        }
      }
      v
    })
    m <- do.call(rbind, rows)
    return(m)
  }
  if (length(m) == 0) {
    m <- matrix(0, nrow = 1, ncol = n_cols)
  } else {
    m <- matrix(as.numeric(m), ncol = n_cols, byrow = TRUE)
  }
  return(m)
}

samples <- unlist(payload$samples)
features <- unlist(payload$features)
labels_row <- unlist(payload$labels_row)
if (is.null(labels_row)) labels_row <- features
labels_row <- sanitize_labels(labels_row, max_len = 60)
labels_col <- unlist(payload$labels_col)
if (is.null(labels_col)) labels_col <- samples

mat <- to_matrix(payload$matrix, length(samples))
dimnames(mat) <- list(labels_row, labels_col)

# column annotations (sample groups)
ann_col <- NULL
if (length(payload$annotations) > 0) {
  ann_list <- payload$annotations
  if (is.data.frame(ann_list)) {
    ann_df <- ann_list
  } else {
    ann_df <- as.data.frame(do.call(rbind, lapply(ann_list, unlist)), stringsAsFactors = FALSE)
  }
  if ("sample" %in% names(ann_df)) {
    rownames(ann_df) <- ann_df$sample
    ann_df$sample <- NULL
  }
  if (ncol(ann_df) > 0) {
    keep <- sapply(ann_df, function(x) length(unique(x)) > 1)
    if (length(keep) > 0 && is.logical(keep)) {
      ann_df <- ann_df[, keep, drop = FALSE]
    }
  }
  ann_col <- if (ncol(ann_df) > 0) ann_df else NULL
}

# row annotations (lipid class / pathway)
ann_row <- NULL
if (length(payload$annotation_row) > 0) {
  ann_list <- payload$annotation_row
  if (is.data.frame(ann_list)) {
    ann_df <- ann_list
  } else {
    ann_df <- as.data.frame(do.call(rbind, lapply(ann_list, unlist)), stringsAsFactors = FALSE)
  }
  if ("feature" %in% names(ann_df)) {
    rownames(ann_df) <- ann_df$feature
    ann_df$feature <- NULL
  }
  if (nrow(ann_df) == nrow(mat) && ncol(ann_df) > 0) {
    rownames(ann_df) <- rownames(mat)
    keep <- sapply(ann_df, function(x) length(unique(x)) > 1)
    if (length(keep) > 0 && is.logical(keep)) {
      ann_df <- ann_df[, keep, drop = FALSE]
    }
    ann_row <- if (ncol(ann_df) > 0) ann_df else NULL
  }
}

group_color_map <- payload$group_color_map
if (is.null(group_color_map)) group_color_map <- list()

annotation_colors <- make_annotation_colors(ann_col, group_color_map)
if (!is.null(ann_row)) {
  annotation_colors <- c(annotation_colors, make_annotation_colors(ann_row, NULL))
}

# color scale and breaks
colorscale <- payload$colorscale
if (is.null(colorscale) || colorscale == "") colorscale <- "RdBu_r"
center_zero <- isTRUE(payload$center_zero)
breaks_info <- make_breaks(mat, center_zero = center_zero, colorscale = colorscale, n = 100)

metric <- payload$metric
if (!(metric %in% c("euclidean", "correlation", "maximum", "manhattan", "canberra", "binary", "minkowski"))) {
  metric <- "euclidean"
}
method <- payload$method
if (!(method %in% c("average", "ward", "single", "complete", "mcquitty", "median", "centroid"))) {
  method <- "average"
}

width <- as.numeric(payload$width)
height <- as.numeric(payload$height)
res <- as.numeric(payload$res)
if (is.na(res) || res <= 0) res <- 120

tick_size <- as.numeric(payload$tick_size)
if (is.na(tick_size)) tick_size <- 11
title_size <- as.numeric(payload$title_size)
if (is.na(title_size)) title_size <- 16
font_family <- as.character(payload$font_family)
if (is.null(font_family) || font_family == "") font_family <- "Liberation Sans"

nrow_mat <- nrow(mat)
ncol_mat <- ncol(mat)

# pheatmap cell sizes are in points; the PNG figure is width/height pixels at res ppi,
# i.e. width/height in points is pixels * 72 / res. Leave room for dendrograms,
# labels, annotation bars, and the color legend.
fig_width_pts <- width * 72 / res
fig_height_pts <- height * 72 / res

cellwidth <- max(6, min(80, (fig_width_pts - 220) / max(ncol_mat, 1)))
cellheight <- max(8, min(30, (fig_height_pts - 180) / max(nrow_mat, 1)))

fontsize_row <- max(6, min(tick_size, cellheight - 2))
fontsize_col <- max(6, min(tick_size, cellwidth - 1))

show_rownames <- isTRUE(payload$show_rownames)
show_colnames <- isTRUE(payload$show_colnames)
angle_col <- 45
if (show_colnames && ncol_mat > 80) show_colnames <- FALSE

treeheight_row <- if (isTRUE(payload$cluster_rows)) 30 else 0
treeheight_col <- if (isTRUE(payload$cluster_cols)) 30 else 0

caption <- as.character(payload$caption)
if (is.null(caption)) caption <- ""

png(file.path(output_dir, "plot.png"), width = width, height = height, units = "px", res = res)

tryCatch({
  pheatmap(
    mat,
    color = breaks_info$palette,
    breaks = breaks_info$breaks,
    cluster_rows = payload$cluster_rows,
    cluster_cols = payload$cluster_cols,
    clustering_distance_rows = metric,
    clustering_distance_cols = metric,
    clustering_method = method,
    scale = "none",
    annotation_col = ann_col,
    annotation_row = ann_row,
    annotation_colors = annotation_colors,
    labels_row = labels_row,
    labels_col = labels_col,
    show_rownames = show_rownames,
    show_colnames = show_colnames,
    fontsize = tick_size,
    fontsize_row = fontsize_row,
    fontsize_col = fontsize_col,
    angle_col = angle_col,
    cellwidth = cellwidth,
    cellheight = cellheight,
    main = payload$title,
    border_color = "#e2e8f0",
    na_col = "#f3f4f6",
    treeheight_row = treeheight_row,
    treeheight_col = treeheight_col
  )
  if (caption != "") {
    upViewport(0)
    grid.text(
      caption,
      x = unit(4, "mm"),
      y = unit(4, "mm"),
      just = c("left", "bottom"),
      gp = gpar(fontsize = 8, col = "#64748b", fontfamily = font_family)
    )
  }
}, finally = {
  dev.off()
})
