"""
Citations — building a stable numbered source index, formatting individual
citations (APA/MLA), and appending a References/Works Cited section.

Deliberately NOT an LLM call. Matching "[N]" markers in a draft to sources
and formatting a citation from title/authors/date/url is pure, deterministic
logic — there's no reasoning task here that benefits from a model, and
every additional LLM call is one more place something could go subtly
wrong (or hit a rate limit) for no real benefit. The Writer is the one
that decides *where* to cite (see writer_agent.py); this module only
turns the numbers it used into a correctly formatted bibliography.

Name-splitting and year-extraction are necessarily heuristic — full names
arrive as plain strings (not pre-split into given/family), and published
dates arrive in whatever shape each source gives them (an ISO datetime
from ArXiv, a bare year from Semantic Scholar, nothing at all from most
web results). This handles typical Western "First Last" name order and
extracts the first 4-digit number as the year; it won't be perfect for
every name format, and that's a reasonable trade-off for a lightweight,
dependency-free formatter over pulling in a full bibliographic library.
"""

import re
from urllib.parse import urlparse

from app.schemas import Document, SourceType, VerifiedClaim

CITATION_MARKER_PATTERN = re.compile(r"\[(\d+)\]")


def build_source_index(verified_claims: list[VerifiedClaim]) -> list[Document]:
    """A stable, deduplicated (by URL, falling back to title) list of
    every source referenced anywhere across all claims, in first-seen
    order. This is the same numbering given to the Writer, so "[3]" means
    the same source in the draft and in the final bibliography."""
    seen: set[str] = set()
    index: list[Document] = []
    for claim in verified_claims:
        for doc in [*claim.supporting_sources, *claim.contradicting_sources]:
            key = doc.url or doc.title
            if key and key not in seen:
                seen.add(key)
                index.append(doc)
    return index


def cited_reference_numbers(draft: str) -> set[int]:
    """Which [N] markers actually appear in the draft — used so the
    bibliography lists only sources the Writer actually cited, not every
    source that happened to be available."""
    return {int(n) for n in CITATION_MARKER_PATTERN.findall(draft)}


def _split_name(full_name: str) -> tuple[str, str]:
    """Returns (last_name, first_and_middle). Assumes typical "First
    [Middle] Last" order; single-word names are treated as a last name
    with no given name."""
    parts = full_name.strip().split()
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[-1], " ".join(parts[:-1])


def _extract_year(published_date: str | None) -> str:
    if not published_date:
        return "n.d."
    match = re.search(r"(\d{4})", published_date)
    return match.group(1) if match else "n.d."


def _domain_from_url(url: str) -> str:
    try:
        netloc = urlparse(url).netloc
        return netloc[4:] if netloc.startswith("www.") else netloc
    except Exception:
        return ""


def _source_display_name(doc: Document) -> str:
    display = {
        SourceType.ARXIV: "arXiv",
        SourceType.SEMANTIC_SCHOLAR: "Semantic Scholar",
        SourceType.OPENALEX: "OpenAlex",
        SourceType.PUBMED: "PubMed",
        SourceType.CROSSREF: "Crossref",
        SourceType.WIKIPEDIA: "Wikipedia",
    }.get(doc.source)
    if display:
        return display
    # WEB (and any future type) falls back to the human-readable domain.
    return _domain_from_url(doc.url) or "Web"


def _apa_author(full_name: str) -> str:
    last, first_middle = _split_name(full_name)
    initials = " ".join(f"{p[0]}." for p in first_middle.split() if p)
    return f"{last}, {initials}" if initials else last


def _apa_authors(authors: list[str]) -> str:
    formatted = [_apa_author(a) for a in authors if a.strip()]
    if not formatted:
        return ""
    if len(formatted) == 1:
        return formatted[0]
    if len(formatted) <= 20:
        return ", ".join(formatted[:-1]) + f", & {formatted[-1]}"
    return ", ".join(formatted[:19]) + f", ... {formatted[-1]}"  # APA's 21+ author rule


def format_apa(doc: Document) -> str:
    authors = _apa_authors(doc.authors)
    year = _extract_year(doc.published_date)
    title = doc.title.strip().rstrip(".")
    source_name = _source_display_name(doc)

    citation = f"{authors} ({year}). {title}." if authors else f"{title}. ({year})."
    citation += f" {source_name}."
    if doc.url:
        citation += f" {doc.url}"
    return citation


def _mla_author(full_name: str) -> str:
    last, first_middle = _split_name(full_name)
    return f"{last}, {first_middle}" if first_middle else last


def format_mla(doc: Document) -> str:
    year = _extract_year(doc.published_date)
    title = doc.title.strip().rstrip(".")
    source_name = _source_display_name(doc)

    if doc.authors:
        author_str = _mla_author(doc.authors[0])
        if len(doc.authors) > 1:
            author_str += ", et al."
        citation = f'{author_str}. "{title}." {source_name}, {year}'
    else:
        citation = f'"{title}." {source_name}, {year}'
    if doc.url:
        citation += f", {doc.url}"
    return citation + "."


CITATION_FORMATTERS = {"apa": format_apa, "mla": format_mla}


def format_citation(doc: Document, style: str = "apa") -> str:
    return CITATION_FORMATTERS.get(style.lower(), format_apa)(doc)


def append_references_section(draft: str, source_index: list[Document], style: str = "apa") -> str:
    """Appends a References (APA) or Works Cited (MLA) section listing
    only the sources actually cited — via [N] markers — in the draft, not
    every source that was available. Returns the draft unchanged if no
    markers are present (e.g. the Writer's no-Gemini fallback draft, which
    has no citation markers to resolve)."""
    cited_numbers = cited_reference_numbers(draft)
    if not cited_numbers:
        return draft

    heading = "Works Cited" if style.lower() == "mla" else "References"
    lines = [draft.rstrip(), "", f"## {heading}", ""]
    for i, doc in enumerate(source_index, start=1):
        if i in cited_numbers:
            lines.append(f"{i}. {format_citation(doc, style)}")
    return "\n".join(lines)
