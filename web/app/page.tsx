"use client";

import { useResearch } from "@/lib/use-research";
import { Hero } from "@/components/research/hero";
import { RunView } from "@/components/research/run-view";
import { CommandMenu } from "@/components/command/command-menu";

export default function HomePage() {
  const research = useResearch();
  const idle = research.phase === "idle";

  return (
    <>
      {idle ? (
        <Hero onSubmit={research.start} />
      ) : (
        <RunView
          phase={research.phase}
          stages={research.stages}
          elapsedMs={research.elapsedMs}
          query={research.query}
          result={research.result}
          error={research.error}
          onCancel={research.cancel}
          onNewSearch={research.reset}
          onRetry={research.retry}
          onFollowUp={research.start}
        />
      )}

      <CommandMenu
        phase={research.phase}
        result={research.result}
        onStart={research.start}
        onReset={research.reset}
      />
    </>
  );
}
