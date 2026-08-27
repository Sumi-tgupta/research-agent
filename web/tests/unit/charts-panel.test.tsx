import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ChartsPanel } from "@/components/research/charts-panel";
import type { ChartSpec } from "@/lib/types";

describe("ChartsPanel", () => {
  it("renders an informative empty state when there are no charts", () => {
    render(<ChartsPanel charts={[]} />);
    expect(screen.getByText(/no chartable data/i)).toBeInTheDocument();
  });

  it("summarises how many charts were extracted", () => {
    const charts: ChartSpec[] = [
      {
        title: "Adoption",
        chart_type: "bar",
        x_label: "Year",
        y_label: "Users",
        labels: ["2023", "2024"],
        values: [10, 20],
      },
    ];
    render(<ChartsPanel charts={charts} />);
    expect(screen.getByText(/1 chart extracted from verified claims/i)).toBeInTheDocument();
  });
});
