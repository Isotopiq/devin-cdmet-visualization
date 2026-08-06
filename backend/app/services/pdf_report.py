import io
import os
import datetime as dt
import json
import math
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml
import numpy as np
import pandas as pd
from PIL import Image, ImageDraw
from fpdf import FPDF
from fpdf.enums import RenderStyle, Corner
import plotly.graph_objects as go

from app import models, schemas
from app.config import settings as app_settings
from app.services.preprocessing import to_dataframe
from app.services.stats import run_statistical_test
from app.services.plots import generate_plot


def _pdf_logo_dir() -> str:
    import os
    path = os.path.join(app_settings.UPLOAD_DIR, "logos")
    os.makedirs(path, exist_ok=True)
    return path


async def get_pdf_footer_logo_path(db) -> Optional[str]:
    from sqlalchemy import select
    result = await db.execute(select(models.SiteSetting).where(models.SiteSetting.key == "pdf_footer_logo"))
    row = result.scalar_one_or_none()
    if row and row.value:
        import os
        full = os.path.join(_pdf_logo_dir(), row.value)
        if os.path.exists(full):
            return full
    return None


async def get_pdf_prepared_by(db) -> Optional[str]:
    from sqlalchemy import select
    result = await db.execute(select(models.SiteSetting).where(models.SiteSetting.key == "pdf_prepared_by"))
    row = result.scalar_one_or_none()
    return row.value if row and row.value else None

warnings.filterwarnings("ignore", category=DeprecationWarning, message=r"(?s).*Kaleido versions less than 1\.0\.0.*")
warnings.filterwarnings("ignore", category=DeprecationWarning, message=r"(?s).*Use of plotly\.io\.kaleido\.scope.*")
warnings.filterwarnings("ignore", category=DeprecationWarning, message=r"(?s).*setDaemon.*")


_ASSET_DIR = Path(__file__).parent.parent / "assets" / "report_template"
_TEMPLATE_CONFIG: Dict[str, Any] = {}


def _load_template_config() -> Dict[str, Any]:
    global _TEMPLATE_CONFIG
    if not _TEMPLATE_CONFIG:
        config_path = _ASSET_DIR / "template_config.yaml"
        if config_path.exists():
            with open(config_path) as f:
                _TEMPLATE_CONFIG = yaml.safe_load(f) or {}
        else:
            _TEMPLATE_CONFIG = {}
    return _TEMPLATE_CONFIG


def _hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _contrast_text(hex_color: str) -> str:
    r, g, b = _hex_to_rgb(hex_color)
    brightness = (r * 299 + g * 587 + b * 114) / 1000
    return "#0d4a3d" if brightness > 128 else "#ffffff"


def _rgba(hex_color: str, alpha: int = 255) -> Tuple[int, int, int, int]:
    r, g, b = _hex_to_rgb(hex_color)
    return r, g, b, alpha


def _color(pdf: FPDF, hex_color: str):
    r, g, b = _hex_to_rgb(hex_color)
    pdf.set_text_color(r, g, b)


def _fill(pdf: FPDF, hex_color: str):
    r, g, b = _hex_to_rgb(hex_color)
    pdf.set_fill_color(r, g, b)


def _draw_color(pdf: FPDF, hex_color: str):
    r, g, b = _hex_to_rgb(hex_color)
    pdf.set_draw_color(r, g, b)


def _named_rgba(name: str, alpha: int = 255) -> Tuple[int, int, int, int]:
    cmap = {
        "white": "#ffffff",
        "teal": "#00c4a8",
        "green": "#22c55e",
        "red": "#ef4444",
        "blue": "#3b82f6",
        "gray": "#94a3b8",
        "amber": "#fbbf24",
        "purple": "#a78bfa",
    }
    return _rgba(cmap.get(name.lower(), name), alpha)


# ───────────────────────────────────────────────────────────────────────────────
# Cover image generation
# ───────────────────────────────────────────────────────────────────────────────

def _gradient_array(width: int, height: int, hex_stops: List[str]) -> np.ndarray:
    colors = np.array([_hex_to_rgb(c) for c in hex_stops], dtype=np.float32)
    stops = np.linspace(0, 1, len(hex_stops))
    xs = np.arange(width)
    ys = np.arange(height)[:, None]
    t = (xs + ys) / (width + height)
    t = np.clip(t, 0, 1)
    idx = np.searchsorted(stops, t, side="right") - 1
    idx = np.clip(idx, 0, len(colors) - 2)
    t0 = stops[idx]
    t1 = stops[idx + 1]
    local = np.where(t1 > t0, (t - t0) / (t1 - t0), 0)[..., None]
    arr = colors[idx] + (colors[idx + 1] - colors[idx]) * local
    return arr.astype(np.uint8)


def _create_cover_png(style_key: str, width_px: int, height_px: int) -> Image.Image:
    cfg = _load_template_config()
    style_cfg = cfg.get("cover_styles", {}).get(style_key) or cfg.get("cover_styles", {}).get("classic", {})
    gradient = style_cfg.get("gradient")
    if not gradient:
        gradient = cfg.get("colors", {}).get("cover_gradient", ["#0d0550", "#1e1070", "#3528aa", "#2b1782"])

    rgb = _gradient_array(width_px, height_px, gradient)
    img = Image.fromarray(rgb, "RGB").convert("RGBA")
    draw = ImageDraw.Draw(img)

    # Subtle radial circle in top-right (approximate the Figma "radial-gradient")
    circle = Image.new("RGBA", (width_px, height_px), (0, 0, 0, 0))
    cdraw = ImageDraw.Draw(circle)
    r = int(min(width_px, height_px) * 0.45)
    cx = int(width_px * 0.85)
    cy = int(height_px * 0.15)
    for i in range(r, 0, -1):
        alpha = int(25 * (i / r))
        cdraw.ellipse([(cx - i, cy - i), (cx + i, cy + i)], fill=(167, 139, 250, alpha))
    img = Image.alpha_composite(img, circle)
    draw = ImageDraw.Draw(img)

    # Network overlay
    network = cfg.get("network", {})
    nodes = network.get("nodes", [])
    edges = network.get("edges", [])
    if nodes and edges:
        svg_min_x, svg_min_y = 140, 0
        svg_w, svg_h = 320, 240
        tx = int(width_px * 0.52)
        ty = 0
        tw = int(width_px * 0.48)
        th = int(height_px * 0.85)

        def to_px(pt):
            x = tx + (pt["x"] - svg_min_x) / svg_w * tw
            y = ty + (pt["y"] - svg_min_y) / svg_h * th
            return x, y

        for a, b in edges:
            if 0 <= a < len(nodes) and 0 <= b < len(nodes):
                x1, y1 = to_px(nodes[a])
                x2, y2 = to_px(nodes[b])
                draw.line([(x1, y1), (x2, y2)], fill=(255, 255, 255, 100), width=1)

        scale = tw / svg_w
        for n in nodes:
            px, py = to_px(n)
            r = max(2, n["r"] * scale)
            fill = _named_rgba(n["c"], int(255 * 0.85))
            draw.ellipse([(px - r, py - r), (px + r, py + r)], fill=fill)

    # Round the corners so the image fits inside the card rounded rect
    radius = int(min(width_px, height_px) * 0.025)
    mask = Image.new("L", (width_px, height_px), 0)
    mdraw = ImageDraw.Draw(mask)
    mdraw.rounded_rectangle([(0, 0), (width_px, height_px)], radius=radius, fill=255)
    img.putalpha(mask)
    return img


# ───────────────────────────────────────────────────────────────────────────────
# PDF document class
# ───────────────────────────────────────────────────────────────────────────────

class _ReportPDF(FPDF):
    def __init__(self, style: Optional[Dict[str, Any]] = None):
        super().__init__("P", "mm", "A4")
        self.cfg = _load_template_config()
        self.style = style or {}
        self._set_fonts()
        self.set_auto_page_break(False)
        self.margin = 12
        self.header_h = 14
        self.footer_h = 14
        self.card_radius = 5

    def _set_fonts(self):
        requested = (self.style.get("font_family") or "").strip()
        builtin = {"Helvetica", "Times", "Courier"}
        if requested in builtin:
            self.font_family = requested
            return

        candidates = [
            (
                "DejaVu",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            ),
            (
                "Liberation",
                "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
                "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            ),
        ]
        # If a specific TTF family was requested, prefer it if present
        if requested:
            for family, regular, bold in candidates:
                if requested.lower() == family.lower() and Path(regular).exists() and Path(bold).exists():
                    self.add_font(family, "", regular)
                    self.add_font(family, "B", bold)
                    self.font_family = family
                    return

        self.font_family = "Helvetica"
        for family, regular, bold in candidates:
            if Path(regular).exists() and Path(bold).exists():
                self.add_font(family, "", regular)
                self.add_font(family, "B", bold)
                self.font_family = family
                return

    def set_body_font(self, size: int = 11, style: str = ""):
        try:
            self.set_font(self.font_family, style, size)
        except RuntimeError:
            self.set_font("Helvetica", style, size)

    def _rounded_rect(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        r: float,
        corners: Optional[Tuple[Any, ...]] = None,
        style: str = "DF",
    ):
        if corners is None:
            corners = (Corner.TOP_LEFT, Corner.TOP_RIGHT, Corner.BOTTOM_LEFT, Corner.BOTTOM_RIGHT)
        render = RenderStyle.DF if style == "DF" else (RenderStyle.F if style == "F" else RenderStyle.D)
        self._draw_rounded_rect(x, y, w, h, render, corners, r)

    # ──────────────────────────────────────────────────────────────────────────
    # Page chrome
    # ──────────────────────────────────────────────────────────────────────────

    def _page_header(self, title: str, organization: str):
        deep = self.cfg.get("colors", {}).get("deep", "#13086a")
        x, y = self.margin, 8
        w = self.w - 2 * self.margin
        _fill(self, deep)
        _draw_color(self, deep)
        self._rounded_rect(x, y, w, self.header_h, 4, style="F")

        _color(self, "#ffffff")
        self.set_body_font(10, "B")
        self.set_xy(x + 5, y + 4)
        self.cell(w * 0.7, 6, title, align="L")
        self.set_body_font(9, "")
        self.set_xy(x + w * 0.65, y + 4)
        self.cell(w * 0.27, 6, organization, align="R")

    def _page_footer(self, page: int, footer_text: str, date_str: str):
        x = self.margin
        w = self.w - 2 * self.margin
        y = self.h - self.footer_h
        logo_path = self.style.get("footer_logo_path")
        logo_w = 0.0
        logo_h = 0.0
        logo_right_edge = self.w - self.margin - 4
        if logo_path and os.path.exists(logo_path):
            try:
                logo_h = self.footer_h - 4
                with Image.open(logo_path) as img:
                    iw, ih = img.size
                    logo_w = logo_h * (iw / ih)
                logo_x = logo_right_edge - logo_w
                logo_y = y + (self.footer_h - logo_h) / 2
                self.image(logo_path, x=logo_x, y=logo_y, h=logo_h)
            except Exception:
                logo_w = 0.0
                logo_h = 0.0

        _color(self, "#94a3b8")
        self.set_body_font(8)
        text_y = y + (self.footer_h - 5) / 2

        if logo_w > 0:
            logo_left_x = logo_right_edge - logo_w
            # Date text on the left
            self.set_xy(x + 4, text_y)
            date_text_w = max(60, logo_left_x - x - 40)
            self.cell(date_text_w, 5, f"Generated {date_str} | {footer_text}", align="L")
            # Page number centered between date and logo
            self.set_xy(logo_left_x - 28, text_y)
            self.cell(24, 5, f"Page {page}", align="R")
        else:
            self.set_xy(x + 4, text_y)
            self.cell(w * 0.8, 5, f"Generated {date_str} | {footer_text}", align="L")
            self.set_xy(x + w * 0.75, text_y)
            self.cell(w * 0.17, 5, f"Page {page}", align="R")

    def _content_card(self, title: str, y: float, h: float) -> float:
        x = self.margin
        w = self.w - 2 * self.margin
        _fill(self, "#ffffff")
        _draw_color(self, "#e2e8f0")
        self._rounded_rect(x, y, w, h, self.card_radius, style="DF")

        _color(self, "#1a1040")
        self.set_body_font(13, "B")
        self.set_xy(x + 6, y + 6)
        self.cell(w - 12, 7, title, align="L")
        return y + 16

    # ──────────────────────────────────────────────────────────────────────────
    # Cover
    # ──────────────────────────────────────────────────────────────────────────

    def _draw_cover(self):
        self.add_page("P")
        style_key = self.style.get("cover_style", "classic")
        style_cfg = self.cfg.get("cover_styles", {}).get(style_key) or self.cfg.get("cover_styles", {}).get("classic", {})
        text_color = style_cfg.get("text_color", "#ffffff")
        accent = style_cfg.get("accent", "#00c4a8")

        page_w = self.w
        margin = self.margin
        card_x = margin
        card_y = 16
        card_w = page_w - 2 * margin
        card_h = 130

        if style_key == "minimal":
            # Light cover card
            _fill(self, "#ffffff")
            _draw_color(self, "#e2e8f0")
            self._rounded_rect(card_x, card_y, card_w, card_h, self.card_radius, style="DF")
            # subtle light gradient overlay
            try:
                px_per_mm = 4
                img = _create_cover_png("minimal", int(card_w * px_per_mm), int(card_h * px_per_mm))
                self.image(img, x=card_x, y=card_y, w=card_w)
            except Exception:
                pass
        else:
            px_per_mm = 4
            img = _create_cover_png(style_key, int(card_w * px_per_mm), int(card_h * px_per_mm))
            self.image(img, x=card_x, y=card_y, w=card_w)

        # Logo
        logo_path = _ASSET_DIR / ("logo.png" if style_key == "minimal" else "logo_white.png")
        if logo_path.exists():
            self.image(str(logo_path), x=card_x + 6, y=card_y + 6, w=35)

        _color(self, text_color)
        # Organization line
        self.set_xy(card_x + 6, card_y + 24)
        self.set_body_font(9, "B")
        organization = self.style.get("organization", "UCLA Metabolomics Center")
        self.cell(card_w * 0.55, 5, organization.upper(), align="L")

        # Title
        self.set_xy(card_x + 6, card_y + 32)
        self.set_body_font(22, "B")
        title = self.style.get("title") or "Statistical Report"
        self.multi_cell(card_w * 0.62, 12, title, align="L")

        # Report type tag
        tag_y = self.get_y() + 4
        report_type = self.style.get("report_type") or "Lipidomics Statistical Report"
        tag_w = self.get_string_width(report_type) + 8
        _fill(self, accent)
        _draw_color(self, accent)
        self._rounded_rect(card_x + 6, tag_y, tag_w, 7, 3, style="F")
        _color(self, _contrast_text(accent))
        self.set_xy(card_x + 6, tag_y + 1.5)
        self.set_body_font(9, "B")
        self.cell(tag_w, 4, report_type, align="C")

        # Description
        desc = self.style.get("description", "")
        if desc:
            _color(self, text_color)
            self.set_xy(card_x + 6, tag_y + 12)
            self.set_body_font(9)
            self.multi_cell(card_w * 0.62, 5, desc, align="L")

        # Tags
        tags = self.style.get("tags") or _default_tags(self.style.get("sections", []))
        tag_list = [t.strip() for t in tags.split(",") if t.strip()][:6]
        tag_y = self.get_y() + 4
        x_off = card_x + 6
        for i, tag in enumerate(tag_list):
            tag_w = self.get_string_width(tag) + 8
            if x_off + tag_w > card_x + card_w * 0.55:
                x_off = card_x + 6
                tag_y += 9
            if i % 2 == 0:
                _fill(self, accent)
                _color(self, _contrast_text(accent))
            else:
                _fill(self, style_cfg.get("gradient", ["#0d0550"])[0] if style_key != "minimal" else "#ffffff")
                _draw_color(self, accent)
                _color(self, accent)
            self._rounded_rect(x_off, tag_y, tag_w, 7, 3, style="F")
            self.set_xy(x_off, tag_y + 1.5)
            self.set_body_font(8, "B")
            self.cell(tag_w, 4, tag, align="C")
            x_off += tag_w + 4

        # Generated date top-right
        _color(self, text_color)
        self.set_body_font(8)
        self.set_xy(card_x + card_w - 50, card_y + 8)
        self.cell(44, 5, f"Generated {self.style.get('date', dt.datetime.utcnow().strftime('%Y-%m-%d'))}", align="R")

        # Report Overview
        overview_y = card_y + card_h + 12
        _color(self, "#1a1040")
        self.set_xy(card_x, overview_y)
        self.set_body_font(16, "B")
        self.cell(card_w, 8, "Report Overview", align="L")

        grid_y = overview_y + 12
        col_w = (card_w - 6) / 2
        row_h = 28
        gap = 5
        meta = [
            ("PRIMARY COMPARISON", self.style.get("primary_comparison") or "—", "#13086a"),
            ("PREPARED FOR", self.style.get("prepared_for") or "—", "#00c4a8"),
            ("REPORT CONTENTS", self.style.get("report_contents") or "Untargeted Lipidomics Report", "#f59e0b"),
            ("PREPARED BY", self.style.get("prepared_by") or "—", "#2b1782"),
        ]
        for i, (label, value, accent_col) in enumerate(meta):
            cx = card_x + (i % 2) * (col_w + gap)
            cy = grid_y + (i // 2) * (row_h + gap)
            self._meta_card(cx, cy, col_w, row_h, label, value, accent_col)

        self._page_footer(self.page_no(), self.style.get("footer_text", "Confidential"), self.style.get("date", dt.datetime.utcnow().strftime('%Y-%m-%d')))

    def _meta_card(self, x: float, y: float, w: float, h: float, label: str, value: str, accent: str):
        _fill(self, "#ffffff")
        _draw_color(self, "#e2e8f0")
        self._rounded_rect(x, y, w, h, 3, style="DF")
        # Colored top bar
        _fill(self, accent)
        _draw_color(self, accent)
        self._rounded_rect(x + 0.5, y, w - 1, 4, 2, corners=(Corner.TOP_LEFT, Corner.TOP_RIGHT), style="F")
        # Label
        _color(self, "#94a3b8")
        self.set_xy(x + 5, y + 8)
        self.set_body_font(8, "B")
        self.cell(w - 10, 5, label, align="L")
        # Value
        _color(self, "#1a1040")
        self.set_xy(x + 5, y + 15)
        self.set_body_font(10, "B")
        self.multi_cell(w - 10, 5, value, align="L")

    # ──────────────────────────────────────────────────────────────────────────
    # Summary / QC summary
    # ──────────────────────────────────────────────────────────────────────────

    def _draw_metric_card(self, x: float, y: float, w: float, h: float, label: str, value: str, accent: str):
        _fill(self, "#ffffff")
        _draw_color(self, "#e2e8f0")
        self._rounded_rect(x, y, w, h, 3, style="DF")
        _fill(self, accent)
        _draw_color(self, accent)
        self._rounded_rect(x + 0.5, y, w - 1, 4, 2, corners=(Corner.TOP_LEFT, Corner.TOP_RIGHT), style="F")
        _color(self, "#94a3b8")
        self.set_xy(x + 5, y + 8)
        self.set_body_font(8, "B")
        self.cell(w - 10, 5, label, align="L")
        _color(self, "#1a1040")
        self.set_xy(x + 5, y + 15)
        self.set_body_font(12, "B")
        self.cell(w - 10, 7, value, align="L")

    def _draw_table(self, x: float, y: float, w: float, headers: List[str], rows: List[List[str]], zebra: bool = False):
        col_w = w / len(headers)
        _fill(self, "#f2f0fb")
        _draw_color(self, "#e2e8f0")
        _color(self, "#1a1040")
        self.set_xy(x, y)
        self.set_body_font(9, "B")
        for h in headers:
            self.cell(col_w, 7, h, border=1, align="L", fill=True)
        self.ln()
        self.set_body_font(9, "")
        for i, row in enumerate(rows):
            if zebra and i % 2 == 1:
                _fill(self, "#fafafa")
            else:
                _fill(self, "#ffffff")
            _color(self, "#1a1040")
            self.set_x(x)
            for cell in row:
                self.cell(col_w, 7, str(cell), border=1, align="L", fill=True)
            self.ln()

    def _summary_page(self, metrics: dict, group_a: str, group_b: str, p_threshold: float):
        self.add_page("P")
        self._page_header(self.style.get("title", "Report"), self.style.get("organization", ""))
        card_y = 26
        card_h = self.h - card_y - self.footer_h - 8
        self._content_card("Summary", card_y, card_h)

        x = self.margin + 6
        y = card_y + 18
        col_w = (self.w - 2 * self.margin - 12 - 6) / 2
        row_h = 22
        gap = 5
        items = [
            ("Features", str(metrics["features"]), "#13086a"),
            ("Samples", str(metrics["samples"]), "#00c4a8"),
            ("Significant features", f"{metrics['significant']} (padj < {p_threshold})", "#f59e0b"),
            ("Up / Down", f"{metrics['up']} / {metrics['down']}", "#2b1782"),
        ]
        if metrics.get("qc_median_cv") is not None:
            items.append(("QC median CV", f"{metrics['qc_median_cv']}%", "#22c55e"))
        if metrics.get("sample_to_blank") is not None:
            items.append(("Sample/Blank ratio", f"{metrics['sample_to_blank']}x", "#3b82f6"))

        for i, (label, value, accent) in enumerate(items):
            cx = x + (i % 2) * (col_w + gap)
            cy = y + (i // 2) * (row_h + gap)
            self._draw_metric_card(cx, cy, col_w, row_h, label, value, accent)

        table_y = y + ((len(items) + 1) // 2) * (row_h + gap) + 6
        group_rows = [[g, str(c)] for g, c in metrics.get("group_counts", {}).items()]
        if group_rows:
            self._draw_table(x, table_y, self.w - 2 * self.margin - 12, ["Group", "Samples"], group_rows, zebra=True)
            table_y += 9 + len(group_rows) * 7

        top = metrics.get("top_features")
        if top:
            _color(self, "#1a1040")
            self.set_xy(x, table_y + 6)
            self.set_body_font(11, "B")
            cmp = f"{group_b} vs {group_a}" if group_b and group_a else ""
            self.cell(0, 7, f"Top significant features ({cmp})", align="L")
            self.ln(9)
            rows = [
                [s.get("feature_id", ""), f"{_safe_float(s.get('log2fc'), 0):.3f}", f"{_safe_float(s.get('padj'), 1):.3e}"]
                for s in top
            ]
            self._draw_table(x, self.get_y(), self.w - 2 * self.margin - 12, ["Feature", "log2FC", "padj"], rows, zebra=True)

        self._page_footer(self.page_no(), self.style.get("footer_text", "Confidential"), self.style.get("date", dt.datetime.utcnow().strftime('%Y-%m-%d')))

    def _qc_summary_page(self, metrics: dict):
        self.add_page("P")
        self._page_header(self.style.get("title", "QC Report"), self.style.get("organization", ""))
        card_y = 26
        card_h = self.h - card_y - self.footer_h - 8
        self._content_card("QC Metrics Summary", card_y, card_h)

        x = self.margin + 6
        y = card_y + 18
        col_w = (self.w - 2 * self.margin - 12 - 6) / 2
        row_h = 22
        gap = 5
        items = [
            ("Total features", str(metrics["num_features"]), "#13086a"),
            ("Total samples", str(metrics["num_samples"]), "#00c4a8"),
            ("Groups", str(metrics["num_groups"]), "#2b1782"),
            ("Missing %", f"{metrics.get('total_missing_pct', 0)}%", "#f59e0b"),
        ]
        qc_cv = metrics.get("qc_median_cv_pct")
        if qc_cv is not None:
            items.append(("QC median CV", f"{qc_cv}%", "#22c55e"))
        blank_ratio = metrics.get("sample_to_blank_median_ratio")
        if blank_ratio is not None:
            items.append(("Sample/Blank ratio", f"{blank_ratio}x", "#3b82f6"))
        items.append(("PCA outliers", str(metrics.get("pca_outlier_count", 0)), "#ef4444"))

        for i, (label, value, accent) in enumerate(items):
            cx = x + (i % 2) * (col_w + gap)
            cy = y + (i // 2) * (row_h + gap)
            self._draw_metric_card(cx, cy, col_w, row_h, label, value, accent)

        table_y = y + ((len(items) + 1) // 2) * (row_h + gap) + 6
        group_rows = [[g, str(c)] for g, c in metrics.get("group_counts", {}).items()]
        if group_rows:
            self._draw_table(x, table_y, self.w - 2 * self.margin - 12, ["Group", "Samples"], group_rows, zebra=True)
            table_y += 9 + len(group_rows) * 7

        cv = metrics.get("group_cv_pct", {})
        if cv:
            _color(self, "#1a1040")
            self.set_xy(x, table_y + 6)
            self.set_body_font(11, "B")
            self.cell(0, 7, "Group median CV %", align="L")
            self.ln(9)
            rows = [[g, f"{v}%" if v is not None else "N/A"] for g, v in cv.items()]
            self._draw_table(x, self.get_y(), self.w - 2 * self.margin - 12, ["Group", "CV %"], rows, zebra=True)

        outliers = metrics.get("pca_outlier_samples") or []
        if outliers:
            self.set_xy(x, self.get_y() + 6)
            self.set_body_font(11, "B")
            self.cell(0, 7, "PCA outlier samples", align="L")
            self.ln(9)
            rows = [[str(s)] for s in outliers]
            self._draw_table(x, self.get_y(), self.w - 2 * self.margin - 12, ["Sample"], rows, zebra=True)

        self._page_footer(self.page_no(), self.style.get("footer_text", "Confidential"), self.style.get("date", dt.datetime.utcnow().strftime('%Y-%m-%d')))

    # ──────────────────────────────────────────────────────────────────────────
    # Plot pages
    # ──────────────────────────────────────────────────────────────────────────

    def _fit_image(self, buffer: io.BytesIO, x: float, y: float, max_w: float, max_h: float):
        img = Image.open(buffer)
        iw, ih = img.size
        aspect = ih / iw
        draw_w = max_w
        draw_h = draw_w * aspect
        if draw_h > max_h:
            draw_h = max_h
            draw_w = draw_h / aspect
        draw_x = x + (max_w - draw_w) / 2
        self.image(buffer, x=draw_x, y=y, w=draw_w, h=draw_h)

    def _plot_page(self, title: str, buffer: io.BytesIO, orientation: str = "P"):
        self.add_page(orientation)
        self._page_header(self.style.get("title", "Report"), self.style.get("organization", ""))
        card_y = 26
        card_h = self.h - card_y - self.footer_h - 8
        img_y = self._content_card(title, card_y, card_h)
        max_w = self.w - 2 * self.margin - 12
        max_h = card_h - 22
        self._fit_image(buffer, self.margin + 6, img_y, max_w, max_h)
        self._page_footer(self.page_no(), self.style.get("footer_text", "Confidential"), self.style.get("date", dt.datetime.utcnow().strftime('%Y-%m-%d')))

    def _plot_pair_page(self, items: List[Tuple[str, io.BytesIO]], orientation: str = "P"):
        """Render up to two plots on one page, stacked vertically."""
        self.add_page(orientation)
        self._page_header(self.style.get("title", "Report"), self.style.get("organization", ""))
        card_y = 26
        card_h = self.h - card_y - self.footer_h - 8
        img_y = self._content_card("QC Plots", card_y, card_h)
        max_w = self.w - 2 * self.margin - 12
        n = len(items)
        gap = 6
        title_h = 6
        slot_h = (card_h - 16 - (n - 1) * gap - n * title_h) / n if n > 0 else card_h - 16
        y = img_y
        for plot_title, buffer in items:
            _color(self, "#1a1040")
            self.set_body_font(10, "B")
            self.set_xy(self.margin + 6, y)
            self.cell(max_w, title_h, plot_title, align="L")
            y += title_h + 2
            self._fit_image(buffer, self.margin + 6, y, max_w, slot_h - title_h - 2)
            y += slot_h + gap
        self._page_footer(self.page_no(), self.style.get("footer_text", "Confidential"), self.style.get("date", dt.datetime.utcnow().strftime('%Y-%m-%d')))

    def _plot_grid_page(self, items: List[Tuple[str, io.BytesIO]], per_page: int = 4):
        """Render up to 4 or 6 plots on one page in a grid."""
        if per_page == 6:
            cols, rows, orientation = 2, 3, "P"
        else:
            cols, rows, orientation = 2, 2, "L"
        self.add_page(orientation)
        self._page_header(self.style.get("title", "Report"), self.style.get("organization", ""))
        card_y = 26
        card_h = self.h - card_y - self.footer_h - 8
        img_y = self._content_card("QC Plots", card_y, card_h)
        max_w = self.w - 2 * self.margin - 12
        max_h = card_h - (img_y - card_y) - 8
        n = min(len(items), per_page)
        gap_x = 6
        gap_y = 8
        title_h = 5
        slot_w = (max_w - (cols - 1) * gap_x) / cols if cols > 0 else max_w
        slot_h = (max_h - (rows - 1) * gap_y - n * title_h) / rows if rows > 0 else max_h
        for i, item in enumerate(items[:per_page]):
            plot_title, buffer = item[0], item[1]
            col = i % cols
            row = i // cols
            x = self.margin + 6 + col * (slot_w + gap_x)
            y = img_y + row * (slot_h + gap_y + title_h)
            _color(self, "#1a1040")
            self.set_body_font(8, "B")
            self.set_xy(x, y)
            self.cell(slot_w, title_h, plot_title, align="L")
            self._fit_image(buffer, x, y + title_h, slot_w, slot_h)
        self._page_footer(self.page_no(), self.style.get("footer_text", "Confidential"), self.style.get("date", dt.datetime.utcnow().strftime('%Y-%m-%d')))

    def _multi_plot_page(self, title: str, buffers: List[io.BytesIO], per_page: int = 4):
        per_page = max(1, min(per_page, 8))
        cols = 1 if per_page == 1 else 2
        rows = (per_page + cols - 1) // cols
        gap_x = 8
        gap_y = 10
        for i in range(0, len(buffers), per_page):
            self.add_page("P")
            self._page_header(self.style.get("title", "Report"), self.style.get("organization", ""))
            card_y = 26
            card_h = self.h - card_y - self.footer_h - 8
            page_title = title
            if len(buffers) > per_page:
                page_title = f"{title} ({i + 1}-{min(i + per_page, len(buffers))})"
            self._content_card(page_title, card_y, card_h)

            max_w = self.w - 2 * self.margin - 12
            max_h = card_h - 22
            slot_w = (max_w - (cols - 1) * gap_x) / cols if cols > 0 else max_w
            slot_h = (max_h - (rows - 1) * gap_y) / rows if rows > 0 else max_h
            img_y = card_y + 18
            for j, buf in enumerate(buffers[i : i + per_page]):
                col = j % cols
                row = j // cols
                x = self.margin + 6 + col * (slot_w + gap_x)
                y = img_y + row * (slot_h + gap_y)
                _fill(self, "#ffffff")
                _draw_color(self, "#e2e8f0")
                self._rounded_rect(x, y, slot_w, slot_h, 3, style="DF")
                self._fit_image(buf, x + 3, y + 3, slot_w - 6, slot_h - 6)
            self._page_footer(self.page_no(), self.style.get("footer_text", "Confidential"), self.style.get("date", dt.datetime.utcnow().strftime('%Y-%m-%d')))

    def _pathways_table_page(self, pathways: List[Dict[str, Any]]):
        self.add_page("P")
        self._page_header(self.style.get("title", "Report"), self.style.get("organization", ""))
        card_y = 26
        card_h = self.h - card_y - self.footer_h - 8
        self._content_card("Pathway Enrichment Results", card_y, card_h)

        x = self.margin + 6
        y = card_y + 18
        w = self.w - 2 * self.margin - 12
        headers = ["Pathway / Term", "p-value", "adj. p-value", "Found", "Total"]
        rows = []
        for p in pathways:
            name = p.get("name") or p.get("pathway_id") or p.get("term_id") or ""
            pval = p.get("pvalue")
            padj = p.get("padj") or p.get("fdr")
            found = p.get("found") or p.get("compound_count") or p.get("intersection_size")
            total = p.get("total") or p.get("pathway_compound_count") or p.get("term_size")
            rows.append([
                str(name)[:50],
                f"{float(pval):.3e}" if pval is not None else "-",
                f"{float(padj):.3e}" if padj is not None else (f"{float(pval):.3e}" if pval is not None else "-"),
                str(found) if found is not None else "-",
                str(total) if total is not None else "-",
            ])
        self._draw_table(x, y, w, headers, rows, zebra=True)
        self._page_footer(self.page_no(), self.style.get("footer_text", "Confidential"), self.style.get("date", dt.datetime.utcnow().strftime('%Y-%m-%d')))


# ───────────────────────────────────────────────────────────────────────────────
# Helpers kept from original module
# ───────────────────────────────────────────────────────────────────────────────

SECTION_TITLES = {
    "summary": "Summary",
    "heatmap_unclustered": "Heatmap - Abundance (Un-clustered)",
    "heatmap_clustered": "Heatmap - Abundance (Clustered)",
    "pca_score": "PCA Score Plot",
    "pca_loadings": "PCA Top Loadings",
    "pca_scree": "PCA Scree Plot",
    "pls_da": "PLS-DA",
    "opls_da": "OPLS-DA",
    "volcano": "Volcano Plot",
    "functional": "Functional Lipid Volcano Plot",
    "food_profile": "Nutritional Metabolic Lipid Profile",
    "chain_space": "Chain Space Analysis",
    "lipid_class": "Lipid Class Distribution",
    "per_lipid_bars": "Individual Feature Bar Plots",
    "biomarker": "Biomarker Discovery",
    "permanova": "PERMANOVA",
    "outlier": "Outlier Analysis",
    "rt_mz": "Retention Time vs m/z",
}


SECTION_LAYOUTS: Dict[str, Dict[str, Any]] = {
    "default": {"width": 1200, "height": 700, "orientation": "P"},
    "heatmap_unclustered": {"width": 1600, "height": 900, "orientation": "L"},
    "heatmap_clustered": {"width": 1600, "height": 900, "orientation": "L"},
    "pca_score": {"width": 1200, "height": 900, "orientation": "P"},
    "pca_loadings": {"width": 1200, "height": 700, "orientation": "P"},
    "pca_scree": {"width": 800, "height": 600, "orientation": "P"},
    "pls_da": {"width": 1400, "height": 900, "orientation": "L"},
    "opls_da": {"width": 1400, "height": 900, "orientation": "L"},
    "volcano": {"width": 1200, "height": 800, "orientation": "P"},
    "per_lipid_bars": {"width": 600, "height": 400, "orientation": "P"},
    "chain_space": {"width": 1200, "height": 900, "orientation": "P"},
}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _groups(dataset: models.Dataset) -> List[str]:
    meta = dataset.sample_metadata or {}
    groups = sorted(set(str(g) for g in meta.values() if g))
    if "Unknown" in groups:
        groups = [g for g in groups if g != "Unknown"] + ["Unknown"]
    return groups


def _comparison(dataset: models.Dataset, group_a: Optional[str], group_b: Optional[str]) -> Tuple[str, str]:
    groups = _groups(dataset)
    if group_a and group_b and group_a in groups and group_b in groups:
        return group_a, group_b
    if len(groups) >= 2:
        return groups[0], groups[1]
    if len(groups) == 1:
        return groups[0], ""
    return "", ""


def _default_tags(sections: List[str]) -> str:
    labels = [SECTION_TITLES.get(s, s).split(" - ")[0].split(" ")[0] for s in sections if s not in ("summary", "cover")]
    # dedup and cap
    seen = set()
    out = []
    for label in labels:
        key = label.lower()
        if key not in seen:
            seen.add(key)
            out.append(label)
    return ", ".join(out[:5])


def _summary_metrics(dataset: models.Dataset, group_a: str, group_b: str, stats_data: List[dict], p_threshold: float) -> dict:
    df = to_dataframe(dataset)
    sample_meta = dataset.sample_metadata or {}
    groups = _groups(dataset)
    group_counts = {g: sum(1 for s in df.columns if sample_meta.get(s) == g) for g in groups}

    missing_total = df.isna().sum().sum()
    total = df.size
    missing_pct = round(missing_total / total * 100, 2) if total else 0.0

    sig_count = sum(1 for s in stats_data if _safe_float(s.get("padj"), 1.0) < p_threshold)
    up_count = sum(
        1
        for s in stats_data
        if _safe_float(s.get("padj"), 1.0) < p_threshold and _safe_float(s.get("log2fc"), 0.0) > 0
    )
    down_count = sig_count - up_count

    def _median_cv(cols):
        if not cols:
            return None
        sub = df[cols]
        with np.errstate(divide="ignore", invalid="ignore"):
            mean = sub.mean(axis=1, skipna=True)
            std = sub.std(axis=1, skipna=True)
            cv = (std / mean).replace([np.inf, -np.inf], np.nan).dropna()
        return round(float(cv.median()) * 100, 2) if not cv.empty else None

    qc_groups = {g for g in groups if "qc" in g.lower()}
    blank_groups = {g for g in groups if any(b in g.lower() for b in ["blank", "solvent", "ntc", "standard", "pool"])}
    qc_median_cv = _median_cv([c for c in df.columns if sample_meta.get(c) in qc_groups])

    sample_to_blank = None
    sample_groups = [g for g in groups if g not in blank_groups and g not in qc_groups]
    blank_cols = [c for c in df.columns if sample_meta.get(c) in blank_groups]
    sample_cols = [c for c in df.columns if sample_meta.get(c) in sample_groups]
    if blank_cols and sample_cols:
        blank_mean = df[blank_cols].mean(axis=1, skipna=True).replace(0, np.nan)
        sample_mean = df[sample_cols].mean(axis=1, skipna=True)
        ratio = (sample_mean / blank_mean).replace([np.inf, -np.inf], np.nan).dropna()
        sample_to_blank = round(float(ratio.median()), 2) if not ratio.empty else None

    top_features = sorted(
        [s for s in stats_data if s.get("padj") is not None],
        key=lambda s: _safe_float(s.get("padj"), 1.0),
    )[:10]

    return {
        "features": df.shape[0],
        "samples": df.shape[1],
        "groups": groups,
        "group_counts": group_counts,
        "missing_pct": missing_pct,
        "significant": sig_count,
        "up": up_count,
        "down": down_count,
        "qc_median_cv": qc_median_cv,
        "sample_to_blank": sample_to_blank,
        "top_features": top_features,
    }


def _fig_to_png(fig_dict: dict, width: int = 1200, height: int = 700, scale: int = 2, keep_title: bool = False) -> io.BytesIO:
    fig = go.Figure(data=fig_dict.get("data", []), layout=fig_dict.get("layout", {}))

    # Strip the figure title because the PDF card already has a title, unless the caller
    # needs the per-plot title (e.g. individual lipid bar plots).
    if not keep_title and fig.layout.title is not None:
        fig.update_layout(title_text="")

    # Tighten the top margin when the title is removed; keep enough room when kept.
    margin = {}
    if fig.layout.margin is not None:
        margin = {
            k: getattr(fig.layout.margin, k)
            for k in ("l", "r", "t", "b")
            if getattr(fig.layout.margin, k) is not None
        }
    if keep_title:
        margin["t"] = max(margin.get("t", 60), 60)
    else:
        margin["t"] = 30
    fig.update_layout(
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        margin=margin,
    )

    buffer = io.BytesIO()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        fig.write_image(buffer, format="png", width=width, height=height, scale=scale)
    buffer.seek(0)
    return buffer


def _section_params(section: str, group_a: str, group_b: str, stats_data: List[dict], req: schemas.PDFReportRequest, selected_groups: Optional[List[str]] = None, dataset: Optional[models.Dataset] = None) -> Optional[dict]:
    params = req.parameters or {}
    p = {"group_a": group_a, "group_b": group_b, "rename_samples": bool(params.get("rename_samples", False))}
    if section == "heatmap_unclustered":
        return {
            "heatmap_type": "abundance",
            "top_n": params.get("heatmap_top_n", 50),
            "scale": params.get("heatmap_scale", "row_zscore"),
            "metric": params.get("heatmap_metric", "euclidean"),
            "method": params.get("heatmap_method", "average"),
            "cluster_rows": params.get("heatmap_cluster_rows", False),
            "cluster_cols": params.get("heatmap_cluster_cols", False),
            "heatmap_style": params.get("heatmap_style"),
            "linkage_color": params.get("heatmap_linkage_color"),
            **p,
        }
    if section == "heatmap_clustered":
        return {
            "heatmap_type": "abundance",
            "top_n": params.get("heatmap_top_n", 50),
            "scale": params.get("heatmap_scale", "row_zscore"),
            "metric": params.get("heatmap_metric", "euclidean"),
            "method": params.get("heatmap_method", "average"),
            "cluster_rows": params.get("heatmap_cluster_rows", True),
            "cluster_cols": params.get("heatmap_cluster_cols", True),
            "heatmap_style": params.get("heatmap_style"),
            "linkage_color": params.get("heatmap_linkage_color"),
            **p,
        }
    if section in ("pca_score", "pca_loadings", "pca_scree"):
        plot_map = {"pca_score": "score", "pca_loadings": "loading", "pca_scree": "scree"}
        return {"plot": plot_map[section], **p}
    if section == "pls_da":
        return {"n_components": 2, "n_perm": req.n_perm, **p}
    if section == "opls_da":
        return {"n_orth": 1, "n_perm": req.n_perm, **p}
    if section == "per_lipid_bars":
        per_page = int(params.get("per_lipid_top_n", req.top_n) or 8)
        top_n = per_page
        if params.get("all_lipids") and dataset is not None:
            top_n = max(top_n, len(dataset.feature_metadata or []))
        return {
            "stats": stats_data,
            "fc_threshold": req.fc_threshold,
            "p_threshold": req.p_threshold,
            "padj_threshold": req.p_threshold,
            "show_labels": req.show_labels,
            "top_n": top_n,
            "per_page": per_page,
            "groups": selected_groups,
            "test": params.get("test", req.test),
            **p,
        }
    if section == "volcano":
        return {
            "stats": stats_data,
            "fc_threshold": req.fc_threshold,
            "p_threshold": req.p_threshold,
            "padj_threshold": req.p_threshold,
            "show_labels": req.show_labels,
            "top_n": req.top_n,
            **p,
        }
    if section == "chain_space" and selected_groups:
        return {"selected_groups": selected_groups, **p}
    if section == "biomarker":
        comps = params.get("biomarker_comparisons") or params.get("comparisons")
        if comps and isinstance(comps, list) and len(comps) > 1:
            return {**p, "comparisons": comps}
        return p
    if section in ("functional", "food_profile", "chain_space", "permanova", "outlier", "lipid_class"):
        return p
    if section == "rt_mz":
        return {}
    return p


def _build_pdf_style(dataset: models.Dataset, project_name: str, req: schemas.PDFReportRequest, group_a: str, group_b: str, sections: List[str], footer_logo_path: Optional[str] = None) -> Dict[str, Any]:
    style = dict(req.style or {})
    style.setdefault("title", req.title or f"{dataset.name} Report")
    style.setdefault("subtitle", req.subtitle or (f"{group_b} vs {group_a}" if group_b and group_a else ""))
    style.setdefault("primary_comparison", f"{group_b} vs {group_a}" if group_a and group_b else "—")
    style.setdefault("prepared_for", req.prepared_for or "—")
    style.setdefault("prepared_by", req.prepared_by or "Metabolomics Platform")
    style.setdefault("report_type", "Lipidomics Statistical Report")
    style.setdefault("report_contents", "Untargeted Lipidomics Report")
    style.setdefault("description", style.get("description") or "Global overview, differential analysis, and individual metabolite intensity plots")
    style.setdefault("tags", style.get("tags") or _default_tags(sections))
    style.setdefault("organization", style.get("organization") or "UCLA Metabolomics Center")
    style.setdefault("footer_text", style.get("footer_text") or "Confidential")
    style.setdefault("date", style.get("date") or dt.datetime.utcnow().strftime('%Y-%m-%d'))
    style.setdefault("cover_style", style.get("cover_style") or "classic")
    style["footer_logo_path"] = footer_logo_path
    style["sections"] = sections
    style["group_a"] = group_a
    style["group_b"] = group_b
    return style


def build_pdf(dataset: models.Dataset, project_name: str, req: schemas.PDFReportRequest, footer_logo_path: Optional[str] = None) -> bytes:
    group_a, group_b = _comparison(dataset, req.group_a, req.group_b)
    sections = [s for s in req.sections if s in SECTION_TITLES]
    params = req.parameters or {}
    selected_groups = params.get("selected_groups") or ([group_a, group_b] if group_a and group_b else [])

    needs_stats = any(s in ("volcano", "per_lipid_bars") for s in sections)
    stats_data = []
    if needs_stats and selected_groups:
        stats_req = schemas.StatsRequest(
            test=params.get("test", req.test),
            group_a=group_a,
            group_b=group_b,
            selected_groups=selected_groups,
            paired=False,
            multiple_testing=req.multiple_testing,
            alpha=req.alpha,
        )
        stats_res = run_statistical_test(dataset, stats_req)
        stats_data = stats_res.get("results", [])

    style = _build_pdf_style(dataset, project_name, req, group_a, group_b, sections, footer_logo_path=footer_logo_path)
    pdf = _ReportPDF(style=style)

    pdf._draw_cover()

    if "summary" in sections:
        metrics = _summary_metrics(dataset, group_a, group_b, stats_data, req.p_threshold)
        pdf._summary_page(metrics, group_a, group_b, req.p_threshold)

    plot_style = req.style or {}
    for section in sections:
        if section == "summary":
            continue
        section_params = _section_params(section, group_a, group_b, stats_data, req, selected_groups=selected_groups, dataset=dataset)
        if section_params is None:
            continue
        plot_type = section
        if section in ("heatmap_unclustered", "heatmap_clustered"):
            plot_type = "heatmap"
        elif section == "pca_score":
            plot_type = "pca"
        elif section == "pca_loadings":
            plot_type = "pca"
        elif section == "pca_scree":
            plot_type = "pca"
        try:
            fig = generate_plot(
                dataset,
                schemas.PlotRequest(plot_type=plot_type, parameters=section_params, style=plot_style),
            )
        except Exception:
            continue

        title = SECTION_TITLES.get(section, section)
        layout = SECTION_LAYOUTS.get(section, SECTION_LAYOUTS["default"])
        if section == "per_lipid_bars":
            if not isinstance(fig, list):
                continue
            per_page = max(1, min(int(section_params.get("per_page", 4)), 8))
            buffers = [_fig_to_png(f, width=600, height=400, scale=2, keep_title=True) for f in fig]
            if buffers:
                pdf._multi_plot_page(title, buffers, per_page=per_page)
        elif section == "chain_space" or section == "biomarker":
            if not isinstance(fig, list):
                fig = [fig]
            for f in fig:
                if not isinstance(f, dict):
                    continue
                img = _fig_to_png(f, width=layout["width"], height=layout["height"], scale=2)
                pdf._plot_page(title, img, orientation=layout.get("orientation", "P"))
        else:
            if isinstance(fig, list):
                fig = fig[0] if fig else None
            if not isinstance(fig, dict):
                continue
            img = _fig_to_png(fig, width=layout["width"], height=layout["height"], scale=2)
            pdf._plot_page(title, img, orientation=layout.get("orientation", "P"))

    return bytes(pdf.output())


def _qc_figure_title(fig: dict, default: str) -> str:
    title = fig.get("layout", {}).get("title")
    if isinstance(title, dict):
        return title.get("text") or default
    if isinstance(title, str):
        return title or default
    return default


def build_pathway_pdf(
    result: Dict[str, Any],
    dataset_name: str = "",
    project_name: str = "",
    title: Optional[str] = None,
    subtitle: Optional[str] = None,
    primary_comparison: Optional[str] = None,
    prepared_for: Optional[str] = None,
    prepared_by: Optional[str] = "Metabolomics Platform",
    report_contents: Optional[str] = "Pathway Mapping Report",
    report_type: Optional[str] = "Pathway Mapping Report",
    description: Optional[str] = None,
    cover_style: Optional[str] = "classic",
    font_family: Optional[str] = None,
    include_table: bool = True,
    footer_logo_path: Optional[str] = None,
) -> bytes:
    # Normalize custom single-figure results
    figures: List[Tuple[str, Dict[str, Any]]] = []
    if isinstance(result, dict):
        if result.get("bar") and isinstance(result["bar"], dict):
            figures.append(("Pathway Enrichment Bar Chart", result["bar"]))
        if result.get("table") and isinstance(result["table"], dict):
            figures.append(("Pathway Results Table", result["table"]))
        if not figures and result.get("data") and isinstance(result.get("data"), list) and result.get("layout") and isinstance(result.get("layout"), dict):
            figures.append(("Pathway Map", result))
    pathways = result.get("pathways") if isinstance(result, dict) else []
    source = result.get("source") if isinstance(result, dict) else None

    style = {
        "title": title or dataset_name or "Pathway Mapping Report",
        "subtitle": subtitle or (f"Source: {source}" if source else ""),
        "report_type": report_type or "Pathway Mapping Report",
        "description": description or f"Pathway enrichment mapping report for {dataset_name}",
        "report_contents": report_contents or "Pathway Mapping Report",
        "organization": "UCLA Metabolomics Center",
        "footer_text": "Confidential",
        "date": dt.datetime.utcnow().strftime('%Y-%m-%d'),
        "cover_style": cover_style or "classic",
        "font_family": font_family,
        "tags": "Pathway, Enrichment, Mapping",
        "primary_comparison": primary_comparison or "—",
        "prepared_for": prepared_for or "—",
        "prepared_by": prepared_by or "Metabolomics Platform",
        "sections": ["summary"],
        "footer_logo_path": footer_logo_path,
    }
    pdf = _ReportPDF(style=style)
    pdf._draw_cover()

    for fig_title, fig in figures:
        try:
            img = _fig_to_png(fig, width=1100, height=700, scale=2)
            pdf._plot_page(fig_title, img, orientation="P")
        except Exception:
            continue

    if include_table and pathways:
        try:
            pdf._pathways_table_page(pathways[:40])
        except Exception:
            pass

    return bytes(pdf.output())


def build_qc_pdf(
    dataset: models.Dataset,
    project_name: str = "",
    selected_groups: list | None = None,
    primary_comparison: str | None = None,
    prepared_for: str | None = None,
    prepared_by: str | None = None,
    report_contents: str | None = None,
    report_type: str | None = None,
    subtitle: str | None = None,
    description: str | None = None,
    cover_style: str | None = None,
    font_family: str | None = None,
    plots_per_page: int = 2,
    plot_layout: Dict[str, str] | None = None,
    footer_logo_path: Optional[str] = None,
) -> bytes:
    from app.services.qc import qc_analysis

    result = qc_analysis(dataset, selected_groups=selected_groups)
    metrics = result["metrics"]
    figures = result.get("figures", {})

    style = {
        "title": dataset.name,
        "subtitle": subtitle or "Quality control overview",
        "report_type": report_type or "QC Report",
        "description": description or "Quality control metrics and diagnostic plots",
        "report_contents": report_contents or "QC Report",
        "organization": "UCLA Metabolomics Center",
        "footer_text": "Confidential",
        "date": dt.datetime.utcnow().strftime('%Y-%m-%d'),
        "cover_style": cover_style or "teal",
        "font_family": font_family,
        "tags": "QC, Metrics, Plots",
        "primary_comparison": primary_comparison or "—",
        "prepared_for": prepared_for or "—",
        "prepared_by": prepared_by or "Metabolomics Platform",
        "sections": ["summary"],
        "footer_logo_path": footer_logo_path,
    }
    plot_layout = plot_layout or {}
    plots_per_page = max(1, min(plots_per_page or 2, 6))
    pdf = _ReportPDF(style=style)
    pdf._draw_cover()
    pdf._qc_summary_page(metrics)

    figure_order = [
        ("tic", "default"),
        ("missing_pct", "default"),
        ("detected_features", "default"),
        ("log2_intensity", "default"),
        ("cv_by_group", "default"),
        ("pca", "pca_score"),
        ("correlation_heatmap", "heatmap_unclustered"),
    ]

    queue: List[Tuple[str, io.BytesIO, str]] = []

    def _flush_queue():
        if not queue:
            return
        try:
            if plots_per_page == 1:
                for plot_title, buffer, orient in queue:
                    pdf._plot_page(plot_title, buffer, orientation=orient)
            elif plots_per_page == 2:
                while len(queue) >= 2:
                    pdf._plot_pair_page(queue[:2], orientation=queue[0][2])
                    queue[:2] = []
                for leftover in queue:
                    pdf._plot_page(leftover[0], leftover[1], orientation=leftover[2])
            elif plots_per_page in (4, 6):
                per_page = plots_per_page
                while len(queue) >= per_page:
                    pdf._plot_grid_page(queue[:per_page], per_page=per_page)
                    queue[:per_page] = []
                if queue:
                    if len(queue) <= 2:
                        if len(queue) == 2:
                            pdf._plot_pair_page(queue, orientation=queue[0][2])
                        elif len(queue) == 1:
                            pdf._plot_page(queue[0][0], queue[0][1], orientation=queue[0][2])
                    else:
                        pdf._plot_grid_page(queue, per_page=per_page)
        except Exception:
            pass
        queue.clear()

    for key, section in figure_order:
        fig = figures.get(key)
        if not isinstance(fig, dict):
            continue
        title = _qc_figure_title(fig, key.replace("_", " ").title())
        try:
            layout = SECTION_LAYOUTS.get(section, SECTION_LAYOUTS["default"])
            img = _fig_to_png(fig, width=layout["width"], height=layout["height"], scale=2)
            orient = layout.get("orientation", "P")
            if plot_layout.get(key) == "single":
                _flush_queue()
                pdf._plot_page(title, img, orientation=orient)
            else:
                queue.append((title, img, orient))
                if len(queue) >= plots_per_page:
                    _flush_queue()
        except Exception:
            continue
    _flush_queue()

    return bytes(pdf.output())
