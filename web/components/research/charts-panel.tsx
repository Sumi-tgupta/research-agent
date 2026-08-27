"use client";

import * as React from "react";
import { useTheme } from "next-themes";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Cell,
} from "recharts";
import { BarChart3 } from "lucide-react";
import type { ChartSpec } from "@/lib/types";

interface ChartsPanelProps {
  charts: ChartSpec[];
}

const BAR_COLORS = ["#2fae7d", "#37b6a1", "#4dd0a6", "#1f8f66", "#5ec9bf"];

export function ChartsPanel({ charts }: ChartsPanelProps) {
  if (charts.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-border/70 p-8 text-center">
        <p className="font-medium">No chartable data</p>
        <p className="mt-1 text-sm text-muted-foreground">
          This run didn&apos;t surface comparable numeric values to chart.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <BarChart3 className="h-4 w-4" />
        <span>
          {charts.length} chart{charts.length === 1 ? "" : "s"} extracted from
          verified claims
        </span>
      </div>
      {charts.map((chart, i) => (
        <ChartCard key={i} chart={chart} />
      ))}
    </div>
  );
}

function ChartCard({ chart }: { chart: ChartSpec }) {
  const { resolvedTheme } = useTheme();
  const isDark = resolvedTheme !== "light";
  const axis = isDark ? "hsl(153 13% 64%)" : "hsl(156 10% 38%)";
  const grid = isDark ? "hsl(165 24% 18%)" : "hsl(150 15% 85%)";
  const tooltipStyle: React.CSSProperties = {
    background: isDark ? "hsl(161 45% 8%)" : "hsl(0 0% 100%)",
    border: `1px solid ${grid}`,
    borderRadius: 12,
    color: isDark ? "hsl(150 26% 92%)" : "hsl(161 45% 12%)",
    fontSize: 12,
  };

  const data = chart.labels.map((label, i) => ({
    name: label,
    value: chart.values[i] ?? 0,
  }));

  return (
    <div className="rounded-xl border border-border/60 bg-card/40 p-4">
      <h3 className="font-display text-base font-semibold">{chart.title}</h3>
      {(chart.x_label || chart.y_label) && (
        <p className="mt-0.5 text-xs text-muted-foreground">
          {chart.y_label}
          {chart.x_label && chart.y_label ? " vs " : ""}
          {chart.x_label}
        </p>
      )}
      <div className="mt-4 h-64 w-full">
        <ResponsiveContainer width="100%" height="100%">
          {chart.chart_type === "line" ? (
            <LineChart data={data} margin={{ top: 8, right: 12, bottom: 4, left: 4 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={grid} vertical={false} />
              <XAxis
                dataKey="name"
                tick={{ fill: axis, fontSize: 12 }}
                tickLine={false}
                axisLine={{ stroke: grid }}
              />
              <YAxis
                tick={{ fill: axis, fontSize: 12 }}
                tickLine={false}
                axisLine={{ stroke: grid }}
                width={44}
              />
              <Tooltip contentStyle={tooltipStyle} cursor={{ stroke: grid }} />
              <Line
                type="monotone"
                dataKey="value"
                stroke="#37b6a1"
                strokeWidth={2.5}
                dot={{ r: 3, fill: "#37b6a1" }}
                activeDot={{ r: 5 }}
              />
            </LineChart>
          ) : (
            <BarChart data={data} margin={{ top: 8, right: 12, bottom: 4, left: 4 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={grid} vertical={false} />
              <XAxis
                dataKey="name"
                tick={{ fill: axis, fontSize: 12 }}
                tickLine={false}
                axisLine={{ stroke: grid }}
              />
              <YAxis
                tick={{ fill: axis, fontSize: 12 }}
                tickLine={false}
                axisLine={{ stroke: grid }}
                width={44}
              />
              <Tooltip
                contentStyle={tooltipStyle}
                cursor={{ fill: isDark ? "hsl(165 24% 18% / 0.4)" : "hsl(150 15% 85% / 0.4)" }}
              />
              <Bar dataKey="value" radius={[6, 6, 0, 0]}>
                {data.map((_, i) => (
                  <Cell key={i} fill={BAR_COLORS[i % BAR_COLORS.length]} />
                ))}
              </Bar>
            </BarChart>
          )}
        </ResponsiveContainer>
      </div>
    </div>
  );
}
