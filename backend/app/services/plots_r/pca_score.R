suppressPackageStartupMessages({
  library(ggplot2)
  library(jsonlite)
})

args <- commandArgs(trailingOnly = TRUE)
input_file <- args[1]
output_dir <- args[2]

payload <- fromJSON(input_file, simplifyDataFrame = TRUE)

df <- as.data.frame(payload$points)
df$pc1 <- as.numeric(df$pc1)
df$pc2 <- as.numeric(df$pc2)

groups <- sort(unique(df$group))
color_map <- stats::setNames(df$color[!duplicated(df$group)][match(groups, df$group[!duplicated(df$group)])], groups)

p <- ggplot(df, aes(x = pc1, y = pc2, color = group, label = sample)) +
  geom_point(size = 3, alpha = 0.8) +
  scale_color_manual(values = color_map, drop = FALSE) +
  labs(
    title = payload$title,
    x = payload$pc1_label,
    y = payload$pc2_label
  ) +
  theme_minimal(base_size = as.numeric(payload$tick_size)) +
  theme(
    plot.title = element_text(size = as.numeric(payload$title_size), face = "bold", hjust = 0.5),
    axis.title = element_text(size = as.numeric(payload$axis_label_size)),
    axis.text = element_text(size = as.numeric(payload$tick_size)),
    legend.position = "right"
  )

png(file.path(output_dir, "plot.png"), width = as.numeric(payload$width), height = as.numeric(payload$height), units = "px", res = 120)
tryCatch({
  print(p)
}, finally = {
  dev.off()
})
