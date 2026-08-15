suppressPackageStartupMessages({
  library(ggplot2)
  library(jsonlite)
})

args <- commandArgs(trailingOnly = TRUE)
input_file <- args[1]
output_dir <- args[2]

payload <- fromJSON(input_file, simplifyDataFrame = FALSE)

plots <- payload$plots
# normalize to data frame; if simplifyDataFrame = FALSE, plots is a list of lists
if (is.data.frame(plots)) {
  plots <- as.data.frame(plots, stringsAsFactors = FALSE)
} else {
  # each row is a list; build a data frame with list columns preserved where needed
  n <- length(plots)
  if (n == 0) {
    plots <- data.frame()
  } else {
    col_names <- names(plots[[1]])
    cols <- lapply(col_names, function(col) {
      vals <- lapply(plots, `[[`, col)
      lens <- vapply(vals, length, integer(1))
      if (identical(col, "values") || any(lens > 1)) {
        I(lapply(vals, function(x) as.numeric(unlist(x))))
      } else {
        # scalar columns: unlist to vector
        unlist(vals)
      }
    })
    plots <- as.data.frame(setNames(cols, col_names), stringsAsFactors = FALSE)
  }
}

# make sure key columns are vectors
groups <- unlist(payload$groups)
group_colors <- unlist(payload$group_colors)

# build color map
default_color <- "#2e6575"
color_map <- stats::setNames(rep(default_color, length(groups)), groups)
if (length(group_colors) > 0) {
  for (i in seq_along(groups)) {
    color_map[[i]] <- group_colors[((i - 1) %% length(group_colors)) + 1]
  }
}

title_size <- as.numeric(payload$title_size)
axis_label_size <- as.numeric(payload$axis_label_size)
tick_size <- as.numeric(payload$tick_size)
width <- as.numeric(payload$width)
height <- as.numeric(payload$height)

plots$mean <- as.numeric(plots$mean)
plots$sem <- as.numeric(plots$sem)

# ensure values is a list column (one vector per row)
if (!is.list(plots$values)) {
  plots$values <- I(lapply(seq_len(nrow(plots)), function(i) as.numeric(unlist(plots$values[i]))))
}

# collapse long tidy data into one row per replicate value for jitter
point_rows <- lapply(seq_len(nrow(plots)), function(i) {
  vals <- as.numeric(unlist(plots$values[[i]]))
  if (length(vals) == 0 || all(is.na(vals))) vals <- NA_real_
  data.frame(
    feature = as.character(plots$feature[i]),
    feature_raw = as.character(plots$feature_raw[i]),
    group = as.character(plots$group[i]),
    value = vals,
    stringsAsFactors = FALSE
  )
})
points_df <- do.call(rbind, point_rows)

# split by feature and render one PNG each
features <- unique(as.character(plots$feature))

for (idx in seq_along(features)) {
  feat <- features[idx]
  sub_summary <- plots[plots$feature == feat, , drop = FALSE]
  sub_points <- points_df[points_df$feature == feat, , drop = FALSE]
  feat_title <- as.character(unique(sub_summary$feature_raw)[1])
  if (is.null(feat_title) || is.na(feat_title) || length(feat_title) == 0) feat_title <- feat

  p <- ggplot(sub_summary, aes(x = group, y = mean, fill = group)) +
    geom_bar(stat = "identity", width = 0.7, color = "white") +
    geom_errorbar(aes(ymin = pmax(mean - sem, 0), ymax = mean + sem), width = 0.2, linewidth = 0.4) +
    geom_jitter(data = sub_points, aes(x = group, y = value), width = 0.1, size = 2, alpha = 0.7) +
    scale_fill_manual(values = color_map, drop = FALSE) +
    labs(title = feat_title, x = NULL, y = "Mean intensity") +
    theme_minimal(base_size = tick_size) +
    theme(
      plot.title = element_text(size = title_size, face = "bold", hjust = 0.5),
      axis.title.y = element_text(size = axis_label_size),
      axis.text = element_text(size = tick_size),
      axis.text.x = element_text(angle = 45, hjust = 1),
      legend.position = "none",
      panel.grid.major.x = element_blank(),
      panel.grid.minor = element_blank()
    )

  png(file.path(output_dir, sprintf("%03d.png", idx)), width = width, height = height, units = "px", res = 120)
  tryCatch({
    print(p)
  }, finally = {
    dev.off()
  })
}
