suppressPackageStartupMessages({
  library(ggplot2)
  library(jsonlite)
})

script_dir <- dirname(sub("^--file=", "", commandArgs(trailingOnly = FALSE)[grep("^--file=", commandArgs(trailingOnly = FALSE))]))
source(file.path(script_dir, "theme_publication.R"))

args <- commandArgs(trailingOnly = TRUE)
input_file <- args[1]
output_dir <- args[2]

payload <- fromJSON(input_file, simplifyDataFrame = TRUE)

df <- as.data.frame(payload$points)
df$pc1 <- as.numeric(df$pc1)
df$pc2 <- as.numeric(df$pc2)

df$group <- as.character(df$group)
df$sample <- as.character(df$sample)

groups <- sort(unique(df$group))
group_color_map <- payload$group_color_map
if (is.null(group_color_map)) group_color_map <- list()
group_color_vec <- unlist(group_color_map)

missing <- setdiff(groups, names(group_color_vec))
if (length(missing) > 0) {
  pal <- discrete_palette(max(length(missing), 3))
  group_color_vec[missing] <- pal[seq_along(missing)]
}

title_size <- as.numeric(payload$title_size)
axis_label_size <- as.numeric(payload$axis_label_size)
tick_size <- as.numeric(payload$tick_size)
width <- as.numeric(payload$width)
height <- as.numeric(payload$height)
res <- as.numeric(payload$res)
if (is.na(res) || res <= 0) res <- 120
font_family <- as.character(payload$font_family)
if (is.null(font_family) || font_family == "") font_family <- "Liberation Sans"

p <- ggplot(df, aes(x = pc1, y = pc2, color = group, label = sample)) +
  geom_point(size = 3, alpha = 0.85, stroke = 0) +
  scale_color_manual(values = group_color_vec, drop = FALSE) +
  labs(
    title = payload$title,
    x = payload$pc1_label,
    y = payload$pc2_label
  ) +
  theme_publication(base_size = tick_size, title_size = title_size, axis_label_size = axis_label_size, font_family = font_family, grid = "x_y", width = width, height = height) +
  theme(legend.position = "right")

png(file.path(output_dir, "plot.png"), width = width, height = height, units = "px", res = res)
tryCatch(print(p), finally = dev.off())
