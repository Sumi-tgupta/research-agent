"""
Chart Rendering — turns a ChartSpec (already extracted and validated —
see agents/chart_agent.py) into a PNG image via matplotlib. Pure
rendering: this module never decides what's chart-worthy or touches the
numbers, it just draws exactly what it's given.
"""

import os

import matplotlib

matplotlib.use("Agg")  # headless — this runs in a backend service, no display available
import matplotlib.pyplot as plt

from app.schemas import ChartSpec


def render_chart(spec: ChartSpec, output_path: str) -> str:
    """Renders a single chart to a PNG at output_path. Returns the same
    path, for convenient chaining."""
    fig, ax = plt.subplots(figsize=(6, 4))

    if spec.chart_type == "line":
        ax.plot(spec.labels, spec.values, marker="o")
    else:
        ax.bar(spec.labels, spec.values)

    ax.set_title(spec.title)
    if spec.x_label:
        ax.set_xlabel(spec.x_label)
    if spec.y_label:
        ax.set_ylabel(spec.y_label)
    plt.setp(ax.get_xticklabels(), rotation=20, ha="right")
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    return output_path


def render_charts(specs: list[ChartSpec], output_dir: str) -> list[str]:
    """Renders each spec to its own numbered PNG in output_dir (created if
    needed). Returns the file paths in the same order as `specs`."""
    os.makedirs(output_dir, exist_ok=True)
    return [render_chart(spec, os.path.join(output_dir, f"chart_{i}.png")) for i, spec in enumerate(specs, start=1)]
