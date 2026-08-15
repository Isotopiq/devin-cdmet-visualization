suppressPackageStartupMessages({
  library(ggplot2)
  library(jsonlite)
  library(ggrepel)
})

script_dir <- dirname(sub("^--file=", "", commandArgs(trailingOnly = FALSE)[grep("^--file=", commandArgs(trailingOnly = FALSE))]))
source(file.path(script_dir, "theme_publication.R"))

args <- commandArgs(trailingOnly = TRUE)
input_file <- args[1]
output_dir <- args[2]

payload <- fromJSON(input_file, simplifyDataFrame = TRUE)

df <- as.data.frame(payload$points)
df$lfc <- as.numeric(df$lfc)
df$neglogp <- as.numeric(df$neglogp)
df$padj <- as.numeric(df$padj)
df$regulation <- factor(df$regulation, levels = c("up", "down", "ns"))

fc_thresh <- as.numeric(payload$fc_threshold)
p_thresh <- as.numeric(payload$p_threshold)

up_color <- payload$up_color
down_color <- payload$down_color
ns_color <- payload$non_significant_color
color_map <- c(up = up_color, down = down_color, ns = ns_color)

label_count <- min(25, nrow(df))
labeled <- df[order(df$neglogp, decreasing = TRUE), ]
labeled <- head(labeled, label_count)

title_size <- as.numeric(payload$title_size)
axis_label_size <- as.numeric(payload$axis_label_size)
tick_size <- as.numeric(payload$tick_size)
width <- as.numeric(payload$width)
height <- as.numeric(payload$height)
res <- as.numeric(payload$res)
if (is.na(res) || res <= 0) res <- 120

p <- ggplot(df, aes(x = lfc, y = neglogp, color = regulation)) +
  geom_point(alpha = 0.8, size = 2.2, stroke = 0) +
  geom_hline(yintercept = -log10(p_thresh), linetype = "dashed", color = "#64748b", linewidth = 0.5) +
  geom_vline(xintercept = c(-fc_thresh, fc_thresh), linetype = "dashed", color = "#64748b", linewidth = 0.5) +
  scale_color_manual(values = color_map, breaks = c("up", "down", "ns"), name = NULL) +
  geom_text_repel(data = labeled, aes(label = name), size = 3, max.overlaps = 30, show.legend = FALSE, family = "DejaVu Sans", box.padding = 0.2, point.padding = 0.15) +
  labs(
    title = payload$title,
    x = expression(Log[2] ~ fold ~ change),
    y = expression(-Log[10] ~ adjusted ~ P ~ value)
  ) +
  theme_publication(base_size = tick_size, title_size = title_size, axis_label_size = axis_label_size, font_family = "DejaVu Sans", grid = "x_y", width = width, height = height)

png(file.path(output_dir, "plot.png"), width = width, height = height, units = "px", res = res)
tryCatch(print(p), finally = dev.off())
