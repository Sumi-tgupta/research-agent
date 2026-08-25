"""
Tests for chart_render.py. Fully real — matplotlib rendering has no
network or LLM dependency, so there's nothing to mock. Uses PIL as an
independent check that the output is a genuinely valid image, not just a
non-empty file.
"""

import os

from PIL import Image

from app.chart_render import render_chart, render_charts
from app.schemas import ChartSpec


def _spec(chart_type: str = "bar") -> ChartSpec:
    return ChartSpec(
        title="Reported caffeine half-life by source",
        chart_type=chart_type,
        x_label="Source",
        y_label="Hours",
        labels=["Pharmacology review", "Metabolism study"],
        values=[5.0, 9.5],
    )


def test_render_chart_creates_a_valid_png(tmp_path):
    output_path = str(tmp_path / "chart.png")

    result_path = render_chart(_spec(), output_path)

    assert result_path == output_path
    assert os.path.exists(output_path)
    img = Image.open(output_path)
    assert img.format == "PNG"
    assert img.size[0] > 0 and img.size[1] > 0


def test_render_chart_supports_line_type(tmp_path):
    output_path = str(tmp_path / "line_chart.png")
    render_chart(_spec(chart_type="line"), output_path)
    assert Image.open(output_path).format == "PNG"


def test_render_charts_creates_numbered_files_in_directory(tmp_path):
    output_dir = str(tmp_path / "charts")

    paths = render_charts([_spec(), _spec()], output_dir)

    assert len(paths) == 2
    assert paths[0].endswith("chart_1.png")
    assert paths[1].endswith("chart_2.png")
    assert all(os.path.exists(p) for p in paths)


def test_render_charts_creates_output_directory_if_missing(tmp_path):
    output_dir = str(tmp_path / "does" / "not" / "exist" / "yet")
    paths = render_charts([_spec()], output_dir)
    assert os.path.exists(paths[0])


def test_render_charts_empty_list_returns_empty_list(tmp_path):
    assert render_charts([], str(tmp_path / "empty")) == []
