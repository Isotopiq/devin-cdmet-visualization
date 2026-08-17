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
title_bold <- isTRUE(payload$title_bold)
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

  # If individual points span more than a ~10x range above the group means,
  # use a log1p y-axis so the mean bars remain visible while still showing outliers.
  max_mean <- suppressWarnings(max(sub_summary$mean, na.rm = TRUE))
  max_value <- suppressWarnings(max(sub_points$value, na.rm = TRUE))
  use_log <- is.finite(max_mean) && is.finite(max_value) && max_mean > 0 && (max_value / max_mean) > 10

  # Build a clean y scale with readable breaks and human-readable labels.
  max_for_axis <- suppressWarnings(max(c(sub_summary$mean + sub_summary$sem, sub_points$value), na.rm = TRUE))
  if (!is.finite(max_for_axis) || max_for_axis <= 0) max_for_axis <- 1

  y_scale <- if (use_log) {
    max_exp <- floor(log10(max_for_axis))
    step <- if (max_exp >= 4) 2 else 1
    exps <- if (max_exp >= step) seq(step, max_exp, by = step) else max_exp
    power_breaks <- 10^exps + 1e-6
    unit <- 10^(max(0, max_exp - 1))
    nice_top <- ceiling(max_for_axis / unit) * unit
    y_breaks <- unique(c(0, power_breaks, nice_top))
    y_breaks <- y_breaks[y_breaks <= nice_top * 1.05]
    scale_y_continuous(trans = "log1p", expand = expansion(mult = c(0, 0.05)),
                       breaks = y_breaks,
                       labels = scales::label_number(scale_cut = c(k = 1e3, M = 1e6, B = 1e9, T = 1e12)))
  } else {
    scale_y_continuous(expand = expansion(mult = c(0, 0.05)),
                       labels = scales::label_number(scale_cut = c(k = 1e3, M = 1e6, B = 1e9, T = 1e12)))
  }

  dodge_width <- 0.8
  p <- ggplot(sub_summary, aes(x = group, y = mean, fill = group)) +
    geom_col(width = bar_width, colour = "black", linewidth = 0.35, position = position_dodge(width = dodge_width)) +
    geom_errorbar(aes(ymin = pmax(mean - sem, 0), ymax = mean + sem, group = group), width = 0.12, linewidth = 0.4, colour = "black", position = position_dodge(width = dodge_width)) +
    geom_point(data = sub_points, aes(x = group, y = value, colour = group, group = group), fill = "white", shape = 21, size = 2.2, stroke = 0.45, position = position_jitterdodge(dodge.width = dodge_width, jitter.width = 0.06, seed = 42)) +
    scale_fill_manual(values = local_colors, drop = FALSE) +
    scale_colour_manual(values = setNames(rep("black", length(groups_used)), groups_used), guide = "none") +
    scale_x_discrete(expand = expansion(add = 0.5)) +
    y_scale +
    labs(title = feat_title, x = NULL, y = "Mean intensity") +
    theme_publication(base_size = tick_size, title_size = title_size, axis_label_size = axis_label_size, font_family = font_family, grid = "none", width = width, height = height, x_labels = groups_used, title_bold = title_bold) +
    theme(
      legend.position = "none",
      plot.title = element_text(hjust = 0.5, face = if (title_bold) "bold" else "plain", size = title_size, colour = "black", family = font_family, margin = margin(b = 4))
    )

  png(file.path(output_dir, sprintf("%03d.png", idx)), width = width, height = height, units = "px", res = res)
  tryCatch(print(p), finally = dev.off())
}
