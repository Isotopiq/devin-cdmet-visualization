suppressPackageStartupMessages({
  library(ggplot2)
  library(jsonlite)
})

args <- commandArgs(trailingOnly = TRUE)
input_file <- args[1]
output_dir <- args[2]

payload <- fromJSON(input_file, simplifyDataFrame = TRUE)

df <- as.data.frame(payload$data)
df$mean <- as.numeric(df$mean)

groups <- payload$groups
color_map <- stats::setNames(unique(df$color[df$group == groups]), groups)
# build named vector in group order
for (g in groups) {
  color_map[[g]] <- unique(df$color[df$group == g])[1]
}

p <- ggplot(df, aes(x = class, y = mean, fill = group)) +
  geom_bar(stat = "identity", position = "dodge", color = "white") +
  scale_fill_manual(values = color_map, drop = FALSE) +
  labs(
    title = payload$title,
    x = "Lipid class",
    y = "Mean total abundance"
  ) +
  theme_minimal(base_size = as.numeric(payload$tick_size)) +
  theme(
    plot.title = element_text(size = as.numeric(payload$title_size), face = "bold", hjust = 0.5),
    axis.title = element_text(size = as.numeric(payload$axis_label_size)),
    axis.text = element_text(size = as.numeric(payload$tick_size)),
    axis.text.x = element_text(angle = 45, hjust = 1),
    legend.position = "bottom"
  )

png(file.path(output_dir, "plot.png"), width = as.numeric(payload$width), height = as.numeric(payload$height), units = "px", res = 120)
tryCatch({
  print(p)
}, finally = {
  dev.off()
})
