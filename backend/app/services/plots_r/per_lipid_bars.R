suppressPackageStartupMessages({
  library(ggplot2)
  library(jsonlite)
})

script_dir <- dirname(sub("^--file=", "", commandArgs(trailingOnly = FALSE)[grep("^--file=", commandArgs(trailingOnly = FALSE))]))
source(file.path(script_dir, "theme_publication.R"))

args <- commandArgs(trailingOnly = TRUE)
input_file <- args[1]
output_dir <- args[2]

payload <- fromJSON(input_file, simplifyDataFrame = FALSE)

# Ensure the 'plots' list is a data frame even when it is empty.
plots <- payload$plots
if (is.data.frame(plots)) {
  plots <- as.data.frame(plots, stringsAsFactors = FALSE)
} else if (length(plots) == 0) {
  plots <- data.frame()
} else {
  col_names <- names(plots[[1]])
  cols <- lapply(col_names, function(col) {
    vals <- lapply(plots, `[[`, col)
    if (identical(col, "values") || any(vapply(vals, length, integer(1)) > 1)) {
      I(lapply(vals, function(x) as.numeric(unlist(x))))
    } else {
      unlist(vals)
    }
  })
  plots <- as.data.frame(setNames(cols, col_names), stringsAsFactors = FALSE)
}

if (nrow(plots) == 0) {
  png(file.path(output_dir, "plot.png"), width = 600, height = 400, units = "px", res = 120)
  print(ggplot() + theme_void() + annotate("text", x = 0.5, y = 0.5, label = "No data"))
  dev.off()
  quit(save = "no")
}

group_color_map <- payload$group_color_map
if (is.null(group_color_map)) group_color_map <- list()
group_color_vec <- unlist(group_color_map)

title_size <- as.numeric(payload$title_size)
axis_label_size <- as.numeric(payload$axis_label_size)
tick_size <- as.numeric(payload$tick_size)
width <- as.numeric(payload$width)
height <- as.numeric(payload$height)
res <- as.numeric(payload$res)
if (is.na(res) || res <= 0) res <- 120
r_theme <- as.character(payload$r_theme)
if (is.null(r_theme) || r_theme == "") r_theme <- "publication"
font_family <- as.character(payload$font_family)
if (is.null(font_family) || font_family == "") font_family <- "Liberation Sans"
bar_width <- as.numeric(payload$bar_width)
if (is.na(bar_width) || bar_width <= 0 || bar_width > 1) bar_width <- 0.55

plots$mean <- as.numeric(plots$mean)
plots$sem <- as.numeric(plots$sem)
if (!is.list(plots$values) && !is.vector(plots$values)) {
  plots$values <- I(lapply(seq_len(nrow(plots)), function(i) as.numeric(unlist(plots$values[i]))))
}

features <- unique(as.character(plots$feature))

for (idx in seq_along(features)) {
  feat <- features[idx]
  sub_summary <- plots[plots$feature == feat, , drop = FALSE]

  sub_points <- do.call(rbind, lapply(seq_len(nrow(sub_summary)), function(i) {
    vals <- as.numeric(unlist(sub_summary$values[[i]]))
    if (length(vals) == 0 || all(is.na(vals))) vals <- NA_real_
    data.frame(
      feature = as.character(sub_summary$feature[i]),
      group = as.character(sub_summary$group[i]),
      value = vals,
      stringsAsFactors = FALSE
    )
  }))

  feat_title <- as.character(unique(sub_summary$feature_raw)[1])
  if (is.null(feat_title) || is.na(feat_title) || feat_title == "") {
    feat_title <- feat
  }

  # Make sure every group used has a color.
  groups_used <- as.character(unique(sub_summary$group))
  local_colors <- group_color_vec[groups_used]
  missing <- groups_used[is.na(local_colors)]
  if (length(missing) > 0) {
    pal <- discrete_palette(max(length(missing), 3))
    local_colors[missing] <- pal[seq_along(missing)]
  }

  p <- ggplot(sub_summary, aes(x = group, y = mean, fill = group)) +
    geom_col(width = bar_width, colour = NA) +
    geom_errorbar(aes(ymin = pmax(mean - sem, 0), ymax = mean + sem), width = 0.2, linewidth = 0.5, colour = "#334155") +
    geom_jitter(data = sub_points, aes(x = group, y = value), width = 0.12, size = 1.8, shape = 21, fill = "white", colour = "#334155", stroke = 0.5, alpha = 0.9) +
    scale_fill_manual(values = local_colors, drop = FALSE) +
    scale_x_discrete(expand = expansion(add = 0.6)) +
    labs(title = feat_title, x = NULL, y = "Mean intensity") +
    theme_publication(base_size = tick_size, title_size = title_size, axis_label_size = axis_label_size, font_family = font_family, grid = "y", width = width, height = height, x_labels = groups_used) +
    theme(legend.position = "none")

  png(file.path(output_dir, sprintf("%03d.png", idx)), width = width, height = height, units = "px", res = res)
  tryCatch(print(p), finally = dev.off())
}
