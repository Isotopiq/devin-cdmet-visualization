suppressPackageStartupMessages({
  library(ggplot2)
  library(grid)
  library(RColorBrewer)
})

# Derive the directory that this R script lives in so other templates can source it.
get_script_dir <- function() {
  args <- commandArgs(trailingOnly = FALSE)
  file_arg <- args[grep("^--file=", args)]
  if (length(file_arg) > 0) {
    return(dirname(sub("^--file=", "", file_arg[1])))
  }
  getwd()
}

# Publication-ready ggplot2 theme used by all R plot templates.
theme_publication <- function(base_size = 11, title_size = 16, axis_label_size = 12,
                              font_family = "Liberation Sans", grid = c("y", "x_y", "none"),
                              width = NULL, height = NULL, x_labels = NULL, y_labels = NULL,
                              title_bold = TRUE) {
  grid <- match.arg(grid)
  scale <- 1
  if (!is.null(width) && !is.null(height) && is.numeric(width) && is.numeric(height) && width > 0 && height > 0) {
    scale <- max(0.8, min(1.3, min(width, height) / 700))
  }
  title_size <- max(11, min(22, title_size * scale))
  axis_label_size <- max(10, min(16, axis_label_size * scale))
  base_size <- max(8, min(13, base_size * scale))

  x_label_info <- .axis_label_params(x_labels, base_size)
  y_label_info <- .axis_label_params(y_labels, base_size, is_x = FALSE)

  t <- theme_classic(base_size = base_size, base_family = font_family) +
    theme(
      plot.title = element_text(size = title_size, face = if (title_bold) "bold" else "plain", hjust = 0, margin = margin(b = 4), family = font_family),
      plot.subtitle = element_text(size = axis_label_size * 0.85, face = "plain", color = "#475569", hjust = 0, margin = margin(b = 14), family = font_family),
      plot.title.position = "plot",
      plot.subtitle.position = "plot",
      axis.title = element_text(size = axis_label_size, face = "bold", color = "black", family = font_family),
      axis.text = element_text(size = base_size, color = "#1f2937", family = font_family),
      axis.text.x = element_text(size = x_label_info$size, angle = x_label_info$angle, hjust = x_label_info$hjust, family = font_family),
      axis.text.y = element_text(size = y_label_info$size, angle = y_label_info$angle, hjust = y_label_info$hjust, family = font_family),
      panel.background = element_rect(fill = "white", colour = NA),
      panel.grid.major.y = if (grid == "none") element_blank() else element_line(colour = "#e5e7eb", linewidth = 0.25),
      panel.grid.major.x = if (grid %in% c("x_y")) element_line(colour = "#e5e7eb", linewidth = 0.25) else element_blank(),
      panel.grid.minor = element_blank(),
      panel.border = element_blank(),
      axis.line = element_line(colour = "black", linewidth = 0.4),
      axis.ticks = element_line(colour = "black", linewidth = 0.3),
      plot.margin = unit(c(0.5, 0.5, 0.5, 0.5), "cm"),
      legend.position = "bottom",
      legend.title = element_text(size = base_size, face = "bold", family = font_family),
      legend.text = element_text(size = base_size - 1, family = font_family),
      strip.background = element_blank(),
      strip.text = element_text(size = axis_label_size, face = "bold", family = font_family)
    )
  t
}

.axis_label_params <- function(labels, base_size, is_x = TRUE) {
  if (is.null(labels) || length(labels) == 0) {
    return(list(size = base_size, angle = 0, hjust = 0.5))
  }
  n <- length(labels)
  chars <- nchar(as.character(labels))
  max_chars <- max(chars, na.rm = TRUE)
  angle <- 0
  hjust <- 0.5
  if (is_x && (max_chars > 12 || n > 12)) {
    angle <- 45
    hjust <- 1
  } else if (!is_x && max_chars > 10) {
    angle <- 0
    hjust <- 1
  }
  size <- max(7, min(base_size, 120 / max(max_chars, 1)))
  list(size = size, angle = angle, hjust = hjust)
}

# Colorblind-friendly discrete palette generator.
discrete_palette <- function(n) {
  if (n <= 8) {
    return(brewer.pal(max(n, 3), "Set2")[1:n])
  }
  if (n <= 12) {
    return(brewer.pal(12, "Set3")[1:n])
  }
  # Fallback hsv expansion for many categories.
  return(hsv(h = seq(0, 1 - 1 / n, length.out = n), s = 0.6, v = 0.85))
}

# Shorten labels and make them unique so pheatmap does not fail on duplicate row names.
sanitize_labels <- function(labels, max_len = 60) {
  if (is.null(labels)) return(NULL)
  labels <- as.character(labels)
  labels[is.na(labels)] <- ""
  labels <- ifelse(nchar(labels) > max_len, paste0(substr(labels, 1, max_len - 2), "..."), labels)
  if (any(duplicated(labels))) {
    dups <- duplicated(labels) | duplicated(labels, fromLast = TRUE)
    labels[dups] <- make.names(labels[dups], unique = TRUE)
  }
  labels
}

# Build pheatmap annotation colors from a data frame and an optional group->color map.
make_annotation_colors <- function(ann_df, group_color_map = NULL) {
  if (is.null(ann_df) || ncol(ann_df) == 0) return(NULL)
  out <- list()
  for (col in names(ann_df)) {
    vals <- unique(as.character(ann_df[[col]]))
    vals <- vals[!is.na(vals)]
    if (col == "group" && !is.null(group_color_map) && length(group_color_map) > 0) {
      cols <- sapply(vals, function(v) {
        c <- group_color_map[[v]]
        if (is.null(c) || is.na(c) || c == "") "#94a3b8" else c
      }, USE.NAMES = FALSE)
      names(cols) <- vals
      out[[col]] <- cols
    } else {
      n <- max(length(vals), 3)
      pal <- discrete_palette(n)
      out[[col]] <- setNames(pal[1:length(vals)], vals)
    }
  }
  out
}

# Map a user-facing colorscale name to an RColorBrewer palette.
build_color_palette <- function(colorscale, n = 100) {
  rev <- grepl("_r$", colorscale)
  base <- sub("_r$", "", colorscale)
  valid <- c(
    "RdBu", "RdYlBu", "BrBG", "PuOr", "PiYG", "PRGn", "RdGy", "PuBuGn",
    "Blues", "Greens", "Greys", "Oranges", "Purples", "Reds",
    "YlOrRd", "YlOrBr", "YlGnBu", "YlGn", "GnBu", "BuPu", "PuBu",
    "PuRd", "OrRd", "BuGn", "Spectral"
  )
  if (!(base %in% valid)) base <- "RdBu"
  pal <- brewer.pal(9, base)
  if (rev) pal <- rev(pal)
  colorRampPalette(pal)(n)
}

# Build symmetric (z-score) or quantile (abundance) breaks and a matching color palette.
make_breaks <- function(mat, center_zero = TRUE, colorscale = "RdBu_r", n = 100) {
  base_pal <- build_color_palette(colorscale, n = n)
  if (center_zero) {
    lim <- max(abs(mat), na.rm = TRUE)
    if (!is.finite(lim) || lim == 0) lim <- 1
    breaks <- seq(-lim, lim, length.out = n + 1)
  } else {
    q <- quantile(as.vector(mat), probs = seq(0, 1, length.out = n + 1), na.rm = TRUE)
    breaks <- unique(q)
    if (length(breaks) < 2) {
      breaks <- seq(min(mat, na.rm = TRUE), max(mat, na.rm = TRUE), length.out = n + 1)
    }
    n <- length(breaks) - 1
    base_pal <- build_color_palette(colorscale, n = n)
  }
  list(breaks = as.numeric(breaks), palette = base_pal)
}
