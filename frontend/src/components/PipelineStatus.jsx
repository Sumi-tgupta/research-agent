// Mirrors app/stream_events.py's STAGE_LABELS / node order on the backend.
// Shown as "pending" placeholders until their first real event arrives, so
// the whole shape of the pipeline is visible from the start, not just
// what's happened so far.
const PIPELINE_STAGES = [
  { key: "planner", label: "Planner" },
  { key: "search_all", label: "Web Search" },
  { key: "retrieve_all", label: "Paper Retrieval" },
  { key: "dedupe_and_rank", label: "Deduplication & Ranking" },
  { key: "fact_check", label: "Fact Checking" },
  { key: "writer", label: "Writer" },
  { key: "reviewer", label: "Reviewer" },
  { key: "add_citations", label: "Citation Generator" },
  { key: "generate_charts", label: "Chart Generator" },
];

export default function PipelineStatus({ query, events, isRunning, streamError }) {
  const seenKeys = new Set(events.map((event) => event.stage));
  const upcoming = PIPELINE_STAGES.filter((stage) => !seenKeys.has(stage.key));
  const nextKey = isRunning && upcoming.length > 0 ? upcoming[0].key : null;

  let index = 0;

  return (
    <div className="research-log">
      <div className="research-log-header">
        <span className="research-log-title">Research log</span>
        <span className="research-log-query">&ldquo;{query}&rdquo;</span>
      </div>

      {events.map((event, i) => {
        index += 1;
        return (
          <LogRow
            key={`${event.stage}-${i}`}
            index={index}
            label={event.label}
            summary={event.summary}
            status={event.errors && event.errors.length > 0 ? "caution" : "done"}
          />
        );
      })}

      {upcoming.map((stage) => {
        index += 1;
        return (
          <LogRow
            key={stage.key}
            index={index}
            label={stage.label}
            summary={null}
            status={stage.key === nextKey ? "running" : "pending"}
          />
        );
      })}

      {streamError && (
        <div className="log-entry">
          <div className="log-index">!!</div>
          <div className="log-body">
            <div className="log-label">Connection issue</div>
            <div className="log-error">{streamError}</div>
          </div>
          <div className="log-stamp status-error">Error</div>
        </div>
      )}
    </div>
  );
}

function LogRow({ index, label, summary, status }) {
  const stampText = { pending: "Pending", running: "Working", done: "Done", caution: "Done, with notes" }[status];

  return (
    <div className={`log-entry ${status === "pending" ? "is-pending" : ""}`}>
      <div className="log-index">{String(index).padStart(2, "0")}</div>
      <div className="log-body">
        <div className="log-label">{label}</div>
        {summary && <div className="log-summary">{summary}</div>}
      </div>
      <div className={`log-stamp status-${status}`}>{stampText}</div>
    </div>
  );
}
