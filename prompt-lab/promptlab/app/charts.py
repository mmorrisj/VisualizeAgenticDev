"""Server-rendered SVG charts: no scripts, no build step. Every chart has a data table beside it."""

from __future__ import annotations

import zlib
from html import escape

# Two-or-more series colours with at least 3:1 contrast on white, distinguishable without colour
# too, because each series also gets its own marker shape.
SERIES = [("#1d4ed8", "circle"), ("#b45309", "square"), ("#047857", "diamond"), ("#7e22ce", "triangle")]
STUDY = "#9ca3af"


def _marker(shape: str, x: float, y: float, colour: str, size: float = 5) -> str:
    if shape == "square":
        return f'<rect x="{x - size:.1f}" y="{y - size:.1f}" width="{2 * size}" height="{2 * size}" fill="{colour}"/>'
    if shape == "diamond":
        pts = f"{x:.1f},{y - size - 1:.1f} {x + size + 1:.1f},{y:.1f} {x:.1f},{y + size + 1:.1f} {x - size - 1:.1f},{y:.1f}"
        return f'<polygon points="{pts}" fill="{colour}"/>'
    if shape == "triangle":
        pts = f"{x:.1f},{y - size - 1:.1f} {x + size + 1:.1f},{y + size:.1f} {x - size - 1:.1f},{y + size:.1f}"
        return f'<polygon points="{pts}" fill="{colour}"/>'
    return f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{size}" fill="{colour}"/>'


def dot_chart(title: str, variants: list[str], models: list[str], points: list[tuple[str, str, float]],
              background: list[tuple[str, str, float]] | None = None, width: int = 680, height: int = 280) -> str:
    """Scores (0 to 1) per prompt variant: one marker per run, one series per model.

    `background` points (the study's runs) are drawn small and grey behind them.
    """
    left, right, top, bottom = 48, 150, 28, 40
    plot_w, plot_h = width - left - right, height - top - bottom
    band = plot_w / max(1, len(variants))
    model_list = list(dict.fromkeys(models))

    def y(score: float) -> float:
        return top + plot_h * (1 - max(0.0, min(1.0, score)))

    def x(variant: str, model: str, index: int, spread: int, shift: float = 0) -> float:
        slot = model_list.index(model) if model in model_list else 0
        base = left + band * variants.index(variant) + band * (slot + 1) / (len(model_list) + 1)
        return base + shift + (index % spread - spread // 2) * 3

    uid = zlib.crc32(title.encode())
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" '
             f'aria-labelledby="t-{uid} d-{uid}" class="chart">',
             f'<title id="t-{uid}">{escape(title)}</title>',
             f'<desc id="d-{uid}">Check score from 0 to 1 for each run, by prompt and model. '
             f'The table after the chart has the same data.</desc>']
    for tick in (0, 0.5, 1):
        parts.append(f'<line x1="{left}" x2="{left + plot_w}" y1="{y(tick):.1f}" y2="{y(tick):.1f}" '
                     f'stroke="#d1d5db"/><text x="{left - 8}" y="{y(tick) + 4:.1f}" text-anchor="end" '
                     f'font-size="12" fill="#374151">{tick:g}</text>')
    for i, variant in enumerate(variants):
        parts.append(f'<text x="{left + band * (i + 0.5):.1f}" y="{height - 14}" text-anchor="middle" '
                     f'font-size="13" fill="#111827">{escape(variant)}</text>')
    counts: dict = {}
    for variant, model, score in background or []:
        if variant in variants and score is not None:
            k = (variant, model)
            counts[k] = counts.get(k, 0) + 1
            # The study's runs sit in their own column, just left of the model's markers, so equal
            # scores never hide them.
            parts.append(f'<circle cx="{x(variant, model, counts[k], 5, -14 if points else 0):.1f}" cy="{y(score):.1f}" r="2.5" '
                         f'fill="{STUDY}" fill-opacity="0.7"/>')
    counts = {}
    for variant, model, score in points:
        if variant in variants and score is not None and model in model_list:
            k = (variant, model)
            counts[k] = counts.get(k, 0) + 1
            colour, shape = SERIES[model_list.index(model) % len(SERIES)]
            parts.append(_marker(shape, x(variant, model, counts[k], 3, 6 if background else 0), y(score), colour))
    legend_x = left + plot_w + 16
    for i, model in enumerate(model_list):
        colour, shape = SERIES[i % len(SERIES)]
        ly = top + 10 + i * 22
        parts.append(_marker(shape, legend_x + 6, ly, colour) +
                     f'<text x="{legend_x + 18}" y="{ly + 4}" font-size="13" fill="#111827">{escape(model)}</text>')
    if background:
        ly = top + 10 + len(model_list) * 22
        parts.append(f'<circle cx="{legend_x + 6}" cy="{ly}" r="3" fill="{STUDY}"/>'
                     f'<text x="{legend_x + 18}" y="{ly + 4}" font-size="13" fill="#374151">the study</text>')
    parts.append("</svg>")
    return "".join(parts)
