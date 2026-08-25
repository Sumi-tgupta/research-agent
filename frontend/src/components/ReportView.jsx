import { useState } from "react";
import ReactMarkdown from "react-markdown";
import { downloadReportPdf } from "../api.js";

export default function ReportView({ result, onReset }) {
  const [downloading, setDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState(null);

  const claims = result.verified_claims || [];
  const counts = claims.reduce((acc, claim) => {
    acc[claim.verdict] = (acc[claim.verdict] || 0) + 1;
    return acc;
  }, {});

  async function handleDownload() {
    setDownloading(true);
    setDownloadError(null);
    try {
      await downloadReportPdf({
        title: result.plan?.original_query || "Research Report",
        finalReport: result.final_report || result.draft,
        chartSpecs: result.chart_specs,
      });
    } catch (err) {
      setDownloadError(err.message);
    } finally {
      setDownloading(false);
    }
  }

  return (
    <div>
      <div className="report-toolbar">
        <button className="text-link-button" onClick={onReset}>
          ← New research
        </button>
        <button className="download-button" onClick={handleDownload} disabled={downloading}>
          {downloading ? "Preparing PDF…" : "Download PDF"}
        </button>
      </div>

      <div className="report-card">
        <div className="report-meta">
          {counts.corroborated > 0 && <span className="meta-chip chip-verified">{counts.corroborated} corroborated</span>}
          {counts.single_source > 0 && <span className="meta-chip chip-caution">{counts.single_source} single-source</span>}
          {counts.contradicted > 0 && <span className="meta-chip chip-alert">{counts.contradicted} contradicted</span>}
          {result.revision_count > 1 && <span className="meta-chip">revised {result.revision_count - 1}×</span>}
        </div>

        <div className="report-body">
          <ReactMarkdown>{result.final_report || result.draft || ""}</ReactMarkdown>
        </div>

        {result.chart_specs && result.chart_specs.length > 0 && (
          <div className="report-charts">
            {result.chart_specs.map((chart, i) => (
              <ChartPreview key={i} chart={chart} />
            ))}
            <div className="chart-caption">Full-resolution charts are embedded in the downloaded PDF.</div>
          </div>
        )}

        {downloadError && <div className="error-banner">{downloadError}</div>}
      </div>
    </div>
  );
}

function ChartPreview({ chart }) {
  const max = Math.max(...chart.values, 1);
  return (
    <div className="chart-preview">
      <div className="chart-preview-title">{chart.title}</div>
      {chart.labels.map((label, i) => (
        <div className="chart-bar-row" key={`${label}-${i}`}>
          <span className="chart-bar-label">{label}</span>
          <div className="chart-bar-track">
            <div className="chart-bar-fill" style={{ width: `${(chart.values[i] / max) * 100}%` }} />
          </div>
          <span className="chart-bar-value">
            {chart.values[i]}
            {chart.y_label ? ` ${chart.y_label}` : ""}
          </span>
        </div>
      ))}
    </div>
  );
}
