/**
 * Talks to the FastAPI backend built in Phases 1-5.
 *
 * The browser's native EventSource only supports GET requests, and the
 * research query is a JSON POST body (query + several options), so this
 * reads the streaming response body directly with fetch() and parses
 * "data: {...}\n\n" frames out of it by hand, rather than using EventSource.
 */

export async function streamResearch(payload, { onEvent, signal }) {
  const response = await fetch("/api/research/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    signal,
  });

  if (!response.ok || !response.body) {
    throw new Error(`Request failed (HTTP ${response.status})`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? ""; // the last piece may be an incomplete frame

    for (const frame of frames) {
      const line = frame.trim();
      if (!line.startsWith("data:")) continue;
      const jsonText = line.slice("data:".length).trim();
      if (!jsonText) continue;
      try {
        onEvent(JSON.parse(jsonText));
      } catch (err) {
        console.error("Failed to parse a stream event", err, jsonText);
      }
    }
  }
}

export async function downloadReportPdf({ title, finalReport, chartSpecs }) {
  const response = await fetch("/api/reports/pdf", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title, final_report: finalReport, chart_specs: chartSpecs ?? [] }),
  });

  if (!response.ok) {
    throw new Error(`PDF request failed (HTTP ${response.status})`);
  }

  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "research_report.pdf";
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
