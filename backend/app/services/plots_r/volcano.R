suppressPackageStartupMessages({
  library(ggplot2)
  library(jsonlite)
  library(ggrepel)
})

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
ns_color <- payload$ns_color

color_map <- c(up = up_color, down = down_color, ns = ns_color)

# label top significant hits
label_count <- min(15, nrow(df))
labeled <- head(df[order(df$neglogp, decreasing = TRUE), ], label_count)

p <- ggplot(df, aes(x = lfc, y = neglogp, color = regulation)) +
  geom_point(alpha = 0.8, size = 2) +
  geom_hline(yintercept = -log10(p_thresh), linetype = "dashed", color = "grey50", linewidth = 0.5) +
  geom_vline(xintercept = c(-fc_thresh, fc_thresh), linetype = "dashed", color = "grey50", linewidth = 0.5) +
  scale_color_manual(values = color_map, breaks = c("up", "down", "ns")) +
  geom_text_repel(data = labeled, aes(label = name), size = 3, max.overlaps = 20, show.legend = FALSE) +
  labs(
    title = payload$title,
    x = expression(Log[2] ~ fold ~ change),
    y = expression(-Log[10] ~ adjusted ~ P ~ value)
  ) +
  theme_minimal(base_size = as.numeric(payload$tick_size)) +
  theme(
    plot.title = element_text(size = as.numeric(payload$title_size), face = "bold", hjust = 0.5),
    axis.title = element_text(size = as.numeric(payload$axis_label_size)),
    axis.text = element_text(size = as.numeric(payload$tick_size)),
    legend.position = "bottom",
    panel.grid.minor = element_blank()
  )

png(file.path(output_dir, "plot.png"), width = as.numeric(payload$width), height = as.numeric(payload$height), units = "px", res = 120)
tryCatch({
  print(p)
}, finally = {
  dev.off()
})
