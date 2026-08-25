"""
Tests for pdf_export.py. Fully real — ReportLab has no network or LLM
dependency. Uses pypdf to extract and verify the actual rendered text
content, and checks chart placement relative to the References heading
rather than just "did a file get created".
"""

import os

from pypdf import PdfReader

from app.chart_render import render_chart
from app.pdf_export import generate_pdf
from app.schemas import ChartSpec

SAMPLE_REPORT = """# Impact of Microplastics

## Introduction
Microplastics are **small plastic particles** found throughout marine environments.

## Do Microplastics Accumulate in Fish Tissue?
Multiple sources confirm this [1][2].

- Found in digestive tracts of numerous species
- Concentrations vary by feeding behavior

## Conclusion
The evidence is compelling, though gaps remain.

## References

1. Lovelace, A. (2023). A Great Paper. Web. https://a.com
2. Hopper, G. (2021). Another Study. arXiv. https://arxiv.org/abs/1234
"""

REPORT_WITHOUT_REFERENCES = """# A Fallback Report

_Gemini was unavailable, so this is an unformatted summary._

## Some Sub-question
- A claim here, unformatted.
"""


def _chart_spec() -> ChartSpec:
    return ChartSpec(
        title="Reported values by source",
        chart_type="bar",
        x_label="Source",
        y_label="Hours",
        labels=["A", "B"],
        values=[5.0, 9.5],
    )


def test_generates_a_valid_multi_section_pdf(tmp_path):
    output_path = str(tmp_path / "report.pdf")

    result = generate_pdf("Impact of Microplastics", SAMPLE_REPORT, output_path)

    assert result == output_path
    assert os.path.exists(output_path)
    reader = PdfReader(output_path)
    full_text = "\n".join(page.extract_text() for page in reader.pages)
    assert "Impact of Microplastics" in full_text
    assert "Introduction" in full_text
    assert "small plastic particles" in full_text
    assert "digestive tracts" in full_text
    assert "References" in full_text
    assert "Lovelace, A." in full_text


def test_bold_markup_renders_as_plain_text_not_literal_asterisks(tmp_path):
    output_path = str(tmp_path / "report.pdf")
    generate_pdf("Title", SAMPLE_REPORT, output_path)

    text = PdfReader(output_path).pages[0].extract_text()
    assert "small plastic particles" in text
    assert "**" not in text  # markdown syntax itself shouldn't leak through


def test_special_characters_are_escaped_and_do_not_break_rendering(tmp_path):
    output_path = str(tmp_path / "report.pdf")
    tricky_report = "# Title\n\nResults showed A < B & C > D in the comparison.\n"

    generate_pdf("Title", tricky_report, output_path)  # should not raise

    text = PdfReader(output_path).pages[0].extract_text()
    assert "A < B & C > D" in text


def test_charts_are_inserted_before_references_section(tmp_path, monkeypatch):
    chart_path = str(tmp_path / "chart.png")
    render_chart(_chart_spec(), chart_path)
    output_path = str(tmp_path / "report.pdf")

    generate_pdf("Title", SAMPLE_REPORT, output_path, chart_image_paths=[chart_path])

    reader = PdfReader(output_path)
    full_text = "\n".join(page.extract_text() for page in reader.pages)
    assert "Data Visualizations" in full_text
    # the visualizations heading should appear before the references
    # heading in the assembled text, not after
    assert full_text.index("Data Visualizations") < full_text.index("References")


def test_charts_appended_at_end_when_no_references_section_exists(tmp_path):
    chart_path = str(tmp_path / "chart.png")
    render_chart(_chart_spec(), chart_path)
    output_path = str(tmp_path / "report.pdf")

    generate_pdf("Title", REPORT_WITHOUT_REFERENCES, output_path, chart_image_paths=[chart_path])

    text = "\n".join(page.extract_text() for page in PdfReader(output_path).pages)
    assert "Data Visualizations" in text


def test_no_charts_means_no_visualizations_section(tmp_path):
    output_path = str(tmp_path / "report.pdf")
    generate_pdf("Title", SAMPLE_REPORT, output_path, chart_image_paths=None)

    text = "\n".join(page.extract_text() for page in PdfReader(output_path).pages)
    assert "Data Visualizations" not in text


def test_handles_long_content_spanning_multiple_pages(tmp_path):
    long_report = "# Long Report\n\n" + "\n\n".join(f"## Section {i}\nSome content for section {i}. " * 20 for i in range(1, 15))
    output_path = str(tmp_path / "long_report.pdf")

    generate_pdf("Long Report", long_report, output_path)

    assert len(PdfReader(output_path).pages) > 1
