import io
import math
import warnings
from typing import Any, Dict, List, Tuple

import numpy as np


def _axis_number(axis_name: str) -> int:
    digits = "".join(ch for ch in str(axis_name) if ch.isdigit())
    return int(digits) if digits else 1


def _parse_plotly_color(color: Any, default: str = "#94a3b8") -> str:
    if color is None:
        return default
    if isinstance(color, (list, tuple)) and color:
        color = color[0]
    if color is None:
        return default
    color = str(color).strip()
    if not color:
        return default
    if color.lower().startswith("rgb("):
        try:
            parts = color[4:-1].split(",")
            return "#{:02x}{:02x}{:02x}".format(int(parts[0]), int(parts[1]), int(parts[2]))
        except Exception:
            return default
    if color.lower().startswith("rgba("):
        try:
            parts = color[5:-1].split(",")
            return "#{:02x}{:02x}{:02x}".format(int(parts[0]), int(parts[1]), int(parts[2]))
        except Exception:
            return default
    return color


def _plotly_to_mpl_marker(symbol: Any) -> str:
    if not symbol:
        return "o"
    symbol = str(symbol).lower()
    mapping = {
        "circle": "o",
        "diamond": "D",
        "square": "s",
        "triangle-up": "^",
        "triangle-down": "v",
        "triangle-left": "<",
        "triangle-right": ">",
        "cross": "+",
        "x": "x",
        "star": "*",
        "pentagon": "p",
        "hexagon": "h",
        "octagon": "8",
    }
    return mapping.get(symbol, "o")


def _plotly_to_mpl_dash(dash: Any) -> str:
    if not dash:
        return "-"
    dash = str(dash).lower()
    mapping = {
        "solid": "-",
        "dash": "--",
        "dot": ":",
        "dashdot": "-.",
        "longdash": "--",
        "longdashdot": "-.",
    }
    return mapping.get(dash, "-")


def _trace_color(trace: Dict[str, Any]) -> str:
    marker = trace.get("marker") or {}
    if not isinstance(marker, dict):
        marker = {}
    line = trace.get("line") or {}
    if not isinstance(line, dict):
        line = {}
    color = marker.get("color")
    if not color:
        color = line.get("color")
    if not color:
        color = trace.get("marker_color")
    if not color:
        color = trace.get("line_color")
    return _parse_plotly_color(color)


def _set_axis_tick_labels(ax, labels: List[Any], axis: str = "x"):
    labels = [str(l) for l in labels]
    n = len(labels)
    rotate = any(len(l) > 8 for l in labels) or n > 12
    step = max(1, n // 40) if axis == "x" else max(1, n // 50)
    ticks = list(range(0, n, step))
    show = [labels[i] for i in ticks]
    if axis == "x":
        ax.set_xticks(ticks)
        ax.set_xticklabels(show, rotation=45 if rotate else 0, ha="right" if rotate else "center", fontsize=6)
    else:
        ax.set_yticks(ticks)
        ax.set_yticklabels(show, fontsize=6)


def _mpl_bar(ax, traces: List[Dict[str, Any]], layout: Dict[str, Any]):
    categories = []
    for t in traces:
        for xi in t.get("x") or []:
            if xi not in categories:
                categories.append(xi)
    x = np.arange(len(categories))
    n = len(traces)
    width = 0.8 / max(n, 1)
    offsets = np.arange(n) - (n - 1) / 2
    for i, t in enumerate(traces):
        y_dict = {c: 0.0 for c in categories}
        for xi, yi in zip(t.get("x") or [], t.get("y") or []):
            if xi in y_dict and yi is not None:
                try:
                    y_dict[xi] = float(yi)
                except (TypeError, ValueError):
                    pass
        y = [y_dict[c] for c in categories]
        color = _trace_color(t)
        label = str(t.get("name", ""))
        ax.bar(x + offsets[i] * width, y, width, label=label, color=color, edgecolor="white", linewidth=0.5, zorder=3)
    _set_axis_tick_labels(ax, categories, axis="x")
    ax.tick_params(axis="y", labelsize=6)


def _mpl_box(ax, traces: List[Dict[str, Any]], layout: Dict[str, Any]):
    data = []
    labels = []
    colors = []
    for t in traces:
        vals = []
        for v in t.get("y") or []:
            if v is None or (isinstance(v, float) and math.isnan(v)):
                continue
            try:
                vals.append(float(v))
            except (TypeError, ValueError):
                pass
        if vals:
            data.append(vals)
            labels.append(str(t.get("name", "")))
            colors.append(_trace_color(t))
    if not data:
        return
    bp = ax.boxplot(data, labels=labels, patch_artist=True, vert=True, showfliers=True, whis=1.5)
    for patch, color in zip(bp["boxes"], colors):
        patch.set_facecolor(color)
        patch.set_alpha(0.7)
    for median in bp["medians"]:
        median.set_color("#1e293b")
    _set_axis_tick_labels(ax, labels, axis="x")
    ax.tick_params(axis="y", labelsize=6)


def _mpl_scatter(ax, traces: List[Dict[str, Any]], layout: Dict[str, Any]):
    for t in traces:
        x = t.get("x") or []
        y = t.get("y") or []
        if not x or not y or len(x) != len(y):
            continue
        try:
            x_vals = [float(v) if v is not None else np.nan for v in x]
            y_vals = [float(v) if v is not None else np.nan for v in y]
        except (TypeError, ValueError):
            x_vals = [str(v) for v in x]
            y_vals = [str(v) for v in y]
            continue
        mode = str(t.get("mode", "markers"))
        color = _trace_color(t)
        marker = t.get("marker") or {}
        if not isinstance(marker, dict):
            marker = {}
        symbol = _plotly_to_mpl_marker(marker.get("symbol"))
        size = marker.get("size", 8)
        if isinstance(size, (list, tuple)) and size:
            size = np.nanmean([float(v) for v in size if v is not None])
        try:
            size = float(size) if size is not None else 8
        except (TypeError, ValueError):
            size = 8
        line = t.get("line") or {}
        if not isinstance(line, dict):
            line = {}
        line_color = _parse_plotly_color(line.get("color"), color)
        line_width = float(line.get("width", 1.5) or 1.5)
        dash = _plotly_to_mpl_dash(line.get("dash"))
        label = str(t.get("name", ""))
        if "lines" in mode and "markers" in mode:
            ax.plot(x_vals, y_vals, color=line_color, linestyle=dash, linewidth=line_width, marker=symbol, markersize=max(3, size / 2), label=label, zorder=3)
        elif "lines" in mode:
            ax.plot(x_vals, y_vals, color=line_color, linestyle=dash, linewidth=line_width, label=label, zorder=3)
        else:
            ax.scatter(x_vals, y_vals, c=color, marker=symbol, s=max(10, size * 4), label=label, edgecolors="white", linewidths=0.5, zorder=3)
    ax.tick_params(axis="both", labelsize=6)


def _mpl_heatmap(fig, ax, trace: Dict[str, Any], layout: Dict[str, Any]):
    try:
        z = np.array(trace.get("z", []), dtype=float)
    except Exception:
        return
    if z.ndim != 2:
        return
    x_labels = trace.get("x") or []
    y_labels = trace.get("y") or []
    colorscale = trace.get("colorscale") or "RdBu_r"
    zmid = trace.get("zmid")

    import matplotlib.pyplot as plt
    import matplotlib.colors as mcolors
    import matplotlib.cm as mcm

    cmap = None
    if isinstance(colorscale, str):
        try:
            cmap = mcm.get_cmap(colorscale)
        except Exception:
            cmap = None
    if cmap is None and isinstance(colorscale, list):
        try:
            stops = []
            colors = []
            for item in colorscale:
                if isinstance(item, (list, tuple)) and len(item) >= 2:
                    stops.append(float(item[0]))
                    colors.append(_parse_plotly_color(item[1], "#000000"))
                else:
                    colors.append(_parse_plotly_color(item, "#000000"))
            if stops and colors:
                cmap = mcolors.LinearSegmentedColormap.from_list("pf", list(zip(stops, colors)))
            elif colors:
                cmap = mcolors.ListedColormap(colors)
        except Exception:
            cmap = None
    if cmap is None:
        try:
            cmap = mcm.get_cmap("RdBu_r")
        except Exception:
            cmap = "viridis"

    if zmid is not None:
        try:
            zmid = float(zmid)
            max_abs = max(abs(float(np.nanmin(z)) - zmid), abs(float(np.nanmax(z)) - zmid), 1e-9)
            vmin = zmid - max_abs
            vmax = zmid + max_abs
        except Exception:
            vmin = float(np.nanmin(z))
            vmax = float(np.nanmax(z))
    else:
        vmin = float(np.nanmin(z))
        vmax = float(np.nanmax(z))

    im = ax.imshow(z, cmap=cmap, vmin=vmin, vmax=vmax, aspect="auto", origin="upper")

    n_x = z.shape[1]
    n_y = z.shape[0]
    x_step = max(1, n_x // 50)
    y_step = max(1, n_y // 50)
    xticks = list(range(0, n_x, x_step))
    yticks = list(range(0, n_y, y_step))
    ax.set_xticks(xticks)
    ax.set_yticks(yticks)
    x_show = [str(x_labels[i]) if i < len(x_labels) else "" for i in xticks]
    y_show = [str(y_labels[i]) if i < len(y_labels) else "" for i in yticks]
    ax.set_xticklabels(x_show, rotation=45, ha="right", fontsize=5)
    ax.set_yticklabels(y_show, fontsize=5)
    try:
        fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    except Exception:
        pass


def fig_to_png_mpl(fig_dict: Dict[str, Any], width: int = 1200, height: int = 700, scale: int = 2, keep_title: bool = False) -> io.BytesIO:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.colors as mcolors
    import matplotlib.cm as mcm

    del mcolors, mcm  # imported for availability; used above in heatmap

    data = fig_dict.get("data") or []
    layout = fig_dict.get("layout") or {}

    if not data:
        fig = plt.Figure(figsize=(width * scale / 100, height * scale / 100), dpi=100)
        ax = fig.add_subplot(111)
        ax.text(0.5, 0.5, "No plot data", ha="center", va="center", transform=ax.transAxes)
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=100, bbox_inches="tight")
        plt.close(fig)
        buf.seek(0)
        return buf

    pairs = []
    for trace in data:
        pair = (trace.get("xaxis", "x"), trace.get("yaxis", "y"))
        if pair not in pairs:
            pairs.append(pair)

    n = len(pairs)
    cols = min(n, 3)
    rows = (n + cols - 1) // cols
    figsize = (width * scale / 100, height * scale / 100)
    fig = plt.Figure(figsize=figsize, dpi=100)
    if n > 1:
        axes = fig.subplots(rows, cols)
        if rows == 1:
            axes = list(axes)
        else:
            axes = axes.flatten().tolist()
    else:
        axes = [fig.add_subplot(1, 1, 1)]

    for i in range(n, len(axes)):
        axes[i].axis("off")

    pair_to_ax = {pair: axes[i] for i, pair in enumerate(pairs)}

    title_text = ""
    title_obj = layout.get("title")
    if isinstance(title_obj, dict):
        title_text = title_obj.get("text", "") or ""
    elif isinstance(title_obj, str):
        title_text = title_obj
    if title_text and keep_title:
        fig.suptitle(title_text, fontsize=12, color="#1e293b", y=0.98)

    for ann in layout.get("annotations", []):
        if not isinstance(ann, dict):
            continue
        text = ann.get("text")
        if not text or ann.get("showarrow", True):
            continue
        xref = ann.get("xref", "paper")
        if xref.startswith("x"):
            xax = xref
            for pair in pairs:
                if pair[0] == xax:
                    pair_to_ax[pair].set_title(str(text), fontsize=9)
                    break
        elif xref == "paper" and n == 1:
            pair_to_ax[pairs[0]].set_title(str(text), fontsize=9)

    for pair, ax in pair_to_ax.items():
        xnum = _axis_number(pair[0])
        ynum = _axis_number(pair[1])
        xkey = f"xaxis{xnum}" if xnum > 1 else "xaxis"
        ykey = f"yaxis{ynum}" if ynum > 1 else "yaxis"
        xax = layout.get(xkey) or {}
        yax = layout.get(ykey) or {}
        if isinstance(xax, dict):
            xt = xax.get("title") or {}
            if isinstance(xt, dict) and xt.get("text"):
                ax.set_xlabel(str(xt["text"]), fontsize=7)
        if isinstance(yax, dict):
            yt = yax.get("title") or {}
            if isinstance(yt, dict) and yt.get("text"):
                ax.set_ylabel(str(yt["text"]), fontsize=7)

    traces_by_axis = {pair: [] for pair in pairs}
    for trace in data:
        pair = (trace.get("xaxis", "x"), trace.get("yaxis", "y"))
        traces_by_axis[pair].append(trace)

    for pair, traces in traces_by_axis.items():
        ax = pair_to_ax[pair]
        types = [str(t.get("type", "scatter")).lower() for t in traces]
        if "heatmap" in types:
            ht = next((t for t in traces if str(t.get("type", "")).lower() == "heatmap"), None)
            if ht:
                _mpl_heatmap(fig, ax, ht, layout)
        elif all(t == "bar" for t in types):
            _mpl_bar(ax, traces, layout)
        elif all(t == "box" for t in types):
            _mpl_box(ax, traces, layout)
        else:
            _mpl_scatter(ax, traces, layout)

    for ax in axes[:n]:
        handles, labels = ax.get_legend_handles_labels()
        if labels:
            try:
                ax.legend(handles, labels, loc="best", fontsize=6, frameon=True)
            except Exception:
                pass

    buf = io.BytesIO()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        fig.tight_layout(rect=[0, 0.03, 1, 0.96] if title_text and keep_title else [0, 0.03, 1, 1])
        fig.savefig(buf, format="png", dpi=100, bbox_inches="tight", pad_inches=0.08)
    plt.close(fig)
    buf.seek(0)
    return buf
