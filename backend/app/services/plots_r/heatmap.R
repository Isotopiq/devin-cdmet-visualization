suppressPackageStartupMessages({
  library(pheatmap)
  library(jsonlite)
  library(RColorBrewer)
})

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
      if (is.null(row)) return(rep(NA_real_, n_cols))
      v <- unlist(row)
      # ensure length matches number of columns
      if (length(v) < n_cols) {
        v <- c(v, rep(NA_real_, n_cols - length(v)))
      } else if (length(v) > n_cols) {
        v <- v[seq_len(n_cols)]
      }
      as.numeric(v)
    })
    m <- do.call(rbind, rows)
    return(m)
  }
  # fallback flat vector / scalar
  if (length(m) == 0) {
    m <- matrix(0, nrow = 1, ncol = n_cols)
  } else {
    m <- matrix(as.numeric(m), ncol = n_cols, byrow = TRUE)
  }
  return(m)
}

samples <- unlist(payload$samples)
features <- unlist(payload$features)
mat <- to_matrix(payload$matrix, length(samples))
dimnames(mat) <- list(features, samples)

# annotation data frame for columns (samples)
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
  ann_col <- ann_df
}

# color scale: support RdBu_r / RdBu; otherwise use RdBu reversed by default
colorscale <- payload$colorscale
if (grepl("_r$", colorscale)) {
  base_name <- sub("_r$", "", colorscale)
  if (base_name %in% rownames(brewer.pal.info)) {
    pal <- rev(brewer.pal(11, base_name))
  } else {
    pal <- rev(brewer.pal(11, "RdBu"))
  }
} else if (colorscale %in% rownames(brewer.pal.info)) {
  pal <- brewer.pal(11, colorscale)
} else {
  pal <- rev(brewer.pal(11, "RdBu"))
}

color_palette <- colorRampPalette(pal)(100)

# map metric to pheatmap clustering_distance string
metric <- payload$metric
if (!(metric %in% c("euclidean", "correlation", "maximum", "manhattan", "canberra", "binary", "minkowski"))) {
  metric <- "euclidean"
}
method <- payload$method
if (!(method %in% c("average", "ward", "single", "complete", "mcquitty", "median", "centroid"))) {
  method <- "average"
}

# use pre-scaled matrix from Python; do not double scale by default
scale_arg <- "none"
if (identical(payload$scale, "row")) {
  scale_arg <- "none"  # already scaled upstream
}

width <- as.numeric(payload$width)
height <- as.numeric(payload$height)
tick_size <- as.numeric(payload$tick_size)

png(file.path(output_dir, "plot.png"), width = width, height = height, units = "px", res = 120)

tryCatch({
  pheatmap(
    mat,
    color = color_palette,
    cluster_rows = payload$cluster_rows,
    cluster_cols = payload$cluster_cols,
    clustering_distance_rows = metric,
    clustering_distance_cols = metric,
    clustering_method = method,
    scale = scale_arg,
    annotation_col = ann_col,
    show_rownames = nrow(mat) <= 80,
    show_colnames = ncol(mat) <= 80,
    fontsize = tick_size,
    fontsize_row = tick_size,
    fontsize_col = tick_size,
    main = payload$title,
    border_color = NA
  )
}, finally = {
  dev.off()
})
