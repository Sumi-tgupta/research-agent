import { useRef, useState } from "react";
import PipelineStatus from "./components/PipelineStatus.jsx";
import QueryForm from "./components/QueryForm.jsx";
import ReportView from "./components/ReportView.jsx";
import { streamResearch } from "./api.js";

export default function App() {
  const [phase, setPhase] = useState("idle"); // idle | running | complete
  const [query, setQuery] = useState("");
  const [events, setEvents] = useState([]);
  const [result, setResult] = useState(null);
  const [streamError, setStreamError] = useState(null);
  const abortRef = useRef(null);

  async function handleSubmit(payload) {
    setQuery(payload.query);
    setEvents([]);
    setResult(null);
    setStreamError(null);
    setPhase("running");

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      await streamResearch(payload, {
        signal: controller.signal,
        onEvent: (event) => {
          if (event.type === "stage") {
            setEvents((prev) => [...prev, event]);
          } else if (event.type === "complete") {
            setResult(event.result);
            setPhase("complete");
          } else if (event.type === "error") {
            setStreamError(event.message);
          }
        },
      });
    } catch (err) {
      if (err.name !== "AbortError") {
        setStreamError(err.message || "Lost connection to the research backend.");
      }
    }
  }

  function handleReset() {
    abortRef.current?.abort();
    setPhase("idle");
    setEvents([]);
    setResult(null);
    setStreamError(null);
  }

  return (
    <div className="app-shell">
      <header className="masthead">
        <span className="masthead-mark">
          <strong>Research Ledger</strong> — multi-agent verification
        </span>
      </header>

      {phase === "idle" && (
        <>
          <h1 className="intro-heading">A research question, verified.</h1>
          <p className="intro-sub">
            Every claim in the final report is checked against multiple independent sources — and flagged, not
            hidden, when those sources disagree.
          </p>
          <QueryForm onSubmit={handleSubmit} disabled={false} />
        </>
      )}

      {phase === "running" && (
        <>
          <PipelineStatus query={query} events={events} isRunning streamError={streamError} />
          {streamError && (
            <div className="form-footer" style={{ marginTop: 16 }}>
              <button className="text-link-button" onClick={handleReset}>
                ← Try again
              </button>
            </div>
          )}
        </>
      )}

      {phase === "complete" && result && <ReportView result={result} onReset={handleReset} />}
    </div>
  );
}
