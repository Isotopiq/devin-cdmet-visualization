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

df <- as.data.frame(payload$data, stringsAsFactors = FALSE)
df$mean <- as.numeric(df$mean)

group_color_map <- payload$group_color_map
if (is.null(group_color_map)) group_color_map <- list()
group_color_vec <- unlist(group_color_map)
if (length(group_color_vec) == 0) group_color_vec <- c("Group" = "#2e6575")

df$group <- as.character(df$group)
df$class <- as.character(df$class)

n_classes <- length(unique(df$class))
n_groups <- length(unique(df$group))

if (n_classes == 1) {
  p <- ggplot(df, aes(x = group, y = mean, fill = group)) +
    geom_col(width = 0.6, color = "white") +
    scale_fill_manual(values = group_color_vec, drop = FALSE) +
    labs(title = payload$title, x = "Group", y = "Mean total abundance")
} else {
  p <- ggplot(df, aes(x = class, y = mean, fill = group)) +
    geom_bar(stat = "identity", position = position_dodge2(width = 0.8, preserve = "single"), color = "white", width = 0.7) +
    scale_fill_manual(values = group_color_vec, drop = FALSE) +
    labs(title = payload$title, x = "Lipid class", y = "Mean total abundance")
}

title_size <- as.numeric(payload$title_size)
axis_label_size <- as.numeric(payload$axis_label_size)
tick_size <- as.numeric(payload$tick_size)
width <- as.numeric(payload$width)
height <- as.numeric(payload$height)
res <- as.numeric(payload$res)
if (is.na(res) || res <= 0) res <- 120

p <- p +
  theme_publication(base_size = tick_size, title_size = title_size, axis_label_size = axis_label_size, font_family = "DejaVu Sans", grid = "y", width = width, height = height) +
  theme(axis.text.x = element_text(angle = 45, hjust = 1))

png(file.path(output_dir, "plot.png"), width = width, height = height, units = "px", res = res)
tryCatch(print(p), finally = dev.off())
