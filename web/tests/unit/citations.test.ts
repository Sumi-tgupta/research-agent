import { describe, it, expect } from "vitest";
import {
  buildSourceIndex,
  resolveCitation,
  citedNumbers,
  sourceLabel,
  sourceKind,
  domainFromUrl,
  extractYear,
  formatAuthors,
  VERDICT_META,
} from "@/lib/citations";
import type { ResearchDocument, VerifiedClaim, SourceType } from "@/lib/types";

function doc(overrides: Partial<ResearchDocument> = {}): ResearchDocument {
  return {
    title: "Untitled",
    authors: [],
    url: "https://example.com/a",
    source: "web" as SourceType,
    ...overrides,
  };
}

function claim(overrides: Partial<VerifiedClaim> = {}): VerifiedClaim {
  return {
    text: "A claim.",
    sub_question: "Q?",
    supporting_sources: [],
    contradicting_sources: [],
    verdict: "single_source",
    confidence: 0.5,
    ...overrides,
  };
}

describe("buildSourceIndex", () => {
  it("dedupes by url||title in first-seen order across supporting then contradicting", () => {
    const a = doc({ title: "A", url: "https://a.test" });
    const b = doc({ title: "B", url: "https://b.test" });
    const c = doc({ title: "C", url: "https://c.test" });
    const claims: VerifiedClaim[] = [
      claim({ supporting_sources: [a, b], contradicting_sources: [a] }),
      claim({ supporting_sources: [c, b] }),
    ];
    const index = buildSourceIndex(claims);
    expect(index.map((d) => d.title)).toEqual(["A", "B", "C"]);
  });

  it("falls back to title when url is empty, and skips entries with neither", () => {
    const titled = doc({ title: "T", url: "" });
    const empty = doc({ title: "", url: "" });
    const index = buildSourceIndex([
      claim({ supporting_sources: [titled, empty, titled] }),
    ]);
    expect(index).toHaveLength(1);
    expect(index[0].title).toBe("T");
  });
});

describe("resolveCitation", () => {
  const index = [doc({ title: "one" }), doc({ title: "two" })];
  it("maps 1-based markers to sources", () => {
    expect(resolveCitation(index, 1)?.title).toBe("one");
    expect(resolveCitation(index, 2)?.title).toBe("two");
  });
  it("returns undefined when out of range", () => {
    expect(resolveCitation(index, 0)).toBeUndefined();
    expect(resolveCitation(index, 3)).toBeUndefined();
  });
});

describe("citedNumbers", () => {
  it("extracts every distinct [N] marker", () => {
    const nums = citedNumbers("Intro [1], then [2] and again [2]. Later [10].");
    expect([...nums].sort((x, y) => x - y)).toEqual([1, 2, 10]);
  });
  it("returns an empty set when there are no markers", () => {
    expect(citedNumbers("no markers here").size).toBe(0);
  });
  it("is stable across repeated calls (global regex lastIndex reset)", () => {
    const first = citedNumbers("[1] [2]");
    const second = citedNumbers("[1] [2]");
    expect([...first]).toEqual([...second]);
  });
});

describe("domainFromUrl", () => {
  it("strips a leading www.", () => {
    expect(domainFromUrl("https://www.example.com/x")).toBe("example.com");
  });
  it("keeps other subdomains", () => {
    expect(domainFromUrl("https://sub.example.org")).toBe("sub.example.org");
  });
  it("returns an empty string for invalid urls", () => {
    expect(domainFromUrl("not a url")).toBe("");
  });
});

describe("sourceLabel / sourceKind", () => {
  it("labels web sources by their domain", () => {
    expect(sourceLabel(doc({ source: "web", url: "https://www.nature.com/x" }))).toBe(
      "nature.com"
    );
  });
  it("falls back to 'Web' when a web url can't be parsed", () => {
    expect(sourceLabel(doc({ source: "web", url: "bogus" }))).toBe("Web");
  });
  it("uses the friendly label for academic sources", () => {
    expect(sourceLabel(doc({ source: "arxiv" }))).toBe("arXiv");
    expect(sourceKind(doc({ source: "semantic_scholar" }))).toBe("Semantic Scholar");
    expect(sourceKind(doc({ source: "web" }))).toBe("Web");
  });
});

describe("extractYear", () => {
  it("pulls the first 4-digit year", () => {
    expect(extractYear("2021-05-03")).toBe("2021");
  });
  it("returns n.d. for missing or year-less input", () => {
    expect(extractYear(null)).toBe("n.d.");
    expect(extractYear(undefined)).toBe("n.d.");
    expect(extractYear("spring")).toBe("n.d.");
  });
});

describe("formatAuthors", () => {
  it("handles zero, one, and two authors", () => {
    expect(formatAuthors([])).toBe("");
    expect(formatAuthors(["Ada"])).toBe("Ada");
    expect(formatAuthors(["Ada", "Grace"])).toBe("Ada & Grace");
  });
  it("uses an Oxford-style ampersand up to max, then et al.", () => {
    expect(formatAuthors(["A", "B", "C"])).toBe("A, B & C");
    expect(formatAuthors(["A", "B", "C", "D"])).toBe("A, B, C et al.");
  });
  it("respects a custom max and ignores blank authors", () => {
    expect(formatAuthors(["A", "B"], 1)).toBe("A et al.");
    expect(formatAuthors(["   ", "X"])).toBe("X");
  });
});

describe("VERDICT_META", () => {
  it("has a label and description for every verdict", () => {
    for (const key of [
      "corroborated",
      "single_source",
      "contradicted",
      "unverified",
    ] as const) {
      expect(VERDICT_META[key].label).toBeTruthy();
      expect(VERDICT_META[key].description).toBeTruthy();
    }
  });
});
