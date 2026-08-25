"""
Tests for app/citations.py. All real — no LLM, no network, so there's
nothing to mock. Covers author-name formatting edge cases (single author,
multiple, none), source-type-specific display names, and that the
bibliography only lists sources the draft actually cited.
"""

from app.citations import (
    append_references_section,
    build_source_index,
    cited_reference_numbers,
    format_apa,
    format_mla,
)
from app.schemas import ClaimVerdict, Document, SourceType, VerifiedClaim


def _doc(
    title: str,
    authors: list[str] | None = None,
    source: SourceType = SourceType.WEB,
    url: str = "https://example.com/a",
    published_date: str | None = None,
) -> Document:
    return Document(title=title, authors=authors or [], source=source, url=url, published_date=published_date)


def _claim(supporting: list[Document], contradicting: list[Document] | None = None) -> VerifiedClaim:
    return VerifiedClaim(
        text="A claim.",
        sub_question="A sub-question?",
        supporting_sources=supporting,
        contradicting_sources=contradicting or [],
        verdict=ClaimVerdict.CORROBORATED,
        confidence=0.7,
    )


# --------------------------------------------------------------- source index

def test_build_source_index_deduplicates_by_url_across_claims():
    shared = _doc("Shared paper", url="https://a.com/shared")
    other = _doc("Other paper", url="https://b.com/other")
    claims = [_claim([shared]), _claim([shared, other])]

    index = build_source_index(claims)

    assert len(index) == 2
    assert index[0].title == "Shared paper"  # first-seen order preserved
    assert index[1].title == "Other paper"


def test_build_source_index_includes_contradicting_sources_too():
    supporting = _doc("Supporting", url="https://a.com")
    contradicting = _doc("Contradicting", url="https://b.com")
    index = build_source_index([_claim([supporting], [contradicting])])

    assert {d.title for d in index} == {"Supporting", "Contradicting"}


# --------------------------------------------------------------- marker parsing

def test_cited_reference_numbers_extracts_all_markers():
    assert cited_reference_numbers("Claim one [1]. Claim two [2][3]. Repeat [1].") == {1, 2, 3}


def test_cited_reference_numbers_empty_when_no_markers():
    assert cited_reference_numbers("A draft with no citations at all.") == set()


# --------------------------------------------------------------- APA formatting

def test_apa_single_author():
    doc = _doc("A Great Paper", authors=["Ada Lovelace"], published_date="2023-05-01T00:00:00")
    citation = format_apa(doc)
    assert citation.startswith("Lovelace, A. (2023). A Great Paper.")
    assert "https://example.com/a" in citation


def test_apa_two_authors_uses_ampersand():
    doc = _doc("A Paper", authors=["Ada Lovelace", "Grace Hopper"], published_date="2020")
    citation = format_apa(doc)
    assert "Lovelace, A., & Hopper, G." in citation


def test_apa_no_authors_leads_with_title():
    doc = _doc("Untitled Web Finding", authors=[], published_date="2021", url="https://www.reuters.com/story")
    citation = format_apa(doc)
    assert citation.startswith("Untitled Web Finding. (2021).")
    assert "reuters.com" in citation  # www. stripped


def test_apa_no_date_uses_nd():
    doc = _doc("Timeless Finding", authors=["Ada Lovelace"], published_date=None)
    assert "(n.d.)" in format_apa(doc)


def test_apa_arxiv_source_name():
    doc = _doc("A Preprint", source=SourceType.ARXIV, url="https://arxiv.org/abs/1234")
    assert "arXiv." in format_apa(doc)


def test_apa_semantic_scholar_source_name():
    doc = _doc("A Paper", source=SourceType.SEMANTIC_SCHOLAR, url="https://semanticscholar.org/paper/x")
    assert "Semantic Scholar." in format_apa(doc)


# --------------------------------------------------------------- MLA formatting

def test_mla_single_author_format():
    doc = _doc("A Great Paper", authors=["Ada Lovelace"], published_date="2023")
    citation = format_mla(doc)
    assert citation.startswith('Lovelace, Ada. "A Great Paper."')


def test_mla_multiple_authors_uses_et_al():
    doc = _doc("A Paper", authors=["Ada Lovelace", "Grace Hopper", "Katherine Johnson"], published_date="2020")
    citation = format_mla(doc)
    assert citation.startswith("Lovelace, Ada, et al.")


def test_mla_no_authors_leads_with_quoted_title():
    doc = _doc("A Finding", authors=[])
    assert format_mla(doc).startswith('"A Finding."')


# --------------------------------------------------------------- References section

def test_references_section_only_lists_cited_sources():
    cited = _doc("Cited Source", authors=["Ada Lovelace"], url="https://a.com")
    uncited = _doc("Uncited Source", url="https://b.com")
    claims = [_claim([cited, uncited])]
    index = build_source_index(claims)  # [cited, uncited] in that order

    draft = "Some finding [1] is well established."
    final = append_references_section(draft, index, style="apa")

    assert "## References" in final
    assert "Cited Source" in final
    assert "Uncited Source" not in final


def test_references_section_uses_mla_heading_and_style():
    doc = _doc("A Paper", authors=["Ada Lovelace"], published_date="2020")
    draft = "A finding [1]."
    final = append_references_section(draft, [doc], style="mla")

    assert "## Works Cited" in final
    assert 'Lovelace, Ada. "A Paper."' in final


def test_references_section_returns_draft_unchanged_if_no_markers():
    draft = "A plain fallback draft with no citation markers."
    doc = _doc("Some Source")
    assert append_references_section(draft, [doc], style="apa") == draft
