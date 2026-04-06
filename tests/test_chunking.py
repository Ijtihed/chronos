"""Tests for the updated RAG chunking strategies — hierarchical + section-based."""

from __future__ import annotations

from backend.hke.ingest import (
    chunk_text,
    hierarchical_chunk_gutenberg,
    section_chunk_wikipedia,
    PARENT_CHUNK_SIZE,
    PARENT_CHUNK_OVERLAP,
    CHILD_CHUNK_SIZE,
    CHILD_CHUNK_OVERLAP,
    WIKI_SECTION_MAX_TOKENS,
)


class TestChunkText:
    def test_basic_chunking(self):
        text = " ".join(f"word{i}" for i in range(100))
        chunks = chunk_text(text, chunk_size=30, overlap=5)
        assert len(chunks) >= 3
        assert all(len(c.split()) <= 30 for c in chunks)

    def test_overlap_produces_shared_content(self):
        text = " ".join(f"word{i}" for i in range(50))
        chunks = chunk_text(text, chunk_size=20, overlap=5)
        if len(chunks) >= 2:
            words_0 = set(chunks[0].split())
            words_1 = set(chunks[1].split())
            assert len(words_0 & words_1) > 0

    def test_empty_text_returns_empty(self):
        assert chunk_text("", 100, 10) == []

    def test_short_text_single_chunk(self):
        text = "hello world"
        chunks = chunk_text(text, 100, 10)
        assert len(chunks) == 1


class TestHierarchicalChunkGutenberg:
    def _make_prose(self, word_count: int) -> str:
        return " ".join(f"word{i}" for i in range(word_count))

    def test_produces_parent_child_structure(self):
        text = self._make_prose(3000)
        hierarchy = hierarchical_chunk_gutenberg(text)
        assert len(hierarchy) >= 2
        for parent_id, parent_text, children in hierarchy:
            assert isinstance(parent_id, str)
            assert len(parent_id) > 0
            assert len(parent_text.split()) <= PARENT_CHUNK_SIZE
            assert len(children) >= 1
            for child_id, child_text in children:
                assert isinstance(child_id, str)
                assert len(child_text.split()) <= CHILD_CHUNK_SIZE

    def test_children_are_subsets_of_parent(self):
        text = self._make_prose(2000)
        hierarchy = hierarchical_chunk_gutenberg(text)
        for _, parent_text, children in hierarchy:
            parent_words = set(parent_text.split())
            for _, child_text in children:
                child_words = set(child_text.split())
                overlap = child_words & parent_words
                assert len(overlap) > len(child_words) * 0.8

    def test_parent_ids_are_unique(self):
        text = self._make_prose(5000)
        hierarchy = hierarchical_chunk_gutenberg(text)
        parent_ids = [pid for pid, _, _ in hierarchy]
        assert len(parent_ids) == len(set(parent_ids))

    def test_child_ids_are_unique(self):
        text = self._make_prose(5000)
        hierarchy = hierarchical_chunk_gutenberg(text)
        child_ids = [cid for _, _, children in hierarchy for cid, _ in children]
        assert len(child_ids) == len(set(child_ids))

    def test_short_text_still_works(self):
        text = "A short passage about history."
        hierarchy = hierarchical_chunk_gutenberg(text)
        assert len(hierarchy) >= 1


class TestSectionChunkWikipedia:
    def test_splits_on_headers(self):
        html = """
        <h2>Early Life</h2>
        <p>Born in 1200 in a small village.</p>
        <h2>Military Career</h2>
        <p>Led the army from 1220 to 1240.</p>
        <h2>Death</h2>
        <p>Died in 1250 during a siege.</p>
        """
        sections = section_chunk_wikipedia(html, "Test Article")
        assert len(sections) >= 3
        titles = [s[1] for s in sections]
        assert "Early Life" in titles
        assert "Military Career" in titles

    def test_preserves_section_titles_in_output(self):
        html = """
        <h2>The Siege</h2>
        <p>The city was surrounded for months.</p>
        """
        sections = section_chunk_wikipedia(html, "Test")
        assert any("Siege" in s[1] for s in sections)

    def test_long_section_gets_split(self):
        long_text = " ".join(f"word{i}" for i in range(1500))
        html = f"<h2>Long Section</h2><p>{long_text}</p>"
        sections = section_chunk_wikipedia(html, "Test")
        assert len(sections) >= 2
        assert any("part" in s[1].lower() for s in sections)

    def test_strips_edit_links(self):
        html = '<h2>History[edit]</h2><p>Some content.</p>'
        sections = section_chunk_wikipedia(html, "Test")
        for _, title, _ in sections:
            assert "[edit]" not in title

    def test_no_headers_produces_single_section(self):
        html = "<p>Just a paragraph with no headers at all.</p>"
        sections = section_chunk_wikipedia(html, "Untitled")
        assert len(sections) >= 1
        assert sections[0][1] == "Untitled"

    def test_empty_html_handled(self):
        sections = section_chunk_wikipedia("", "Empty")
        assert isinstance(sections, list)

    def test_chunk_ids_are_unique(self):
        html = """
        <h2>A</h2><p>Text A.</p>
        <h2>B</h2><p>Text B.</p>
        <h3>B.1</h3><p>Text B1.</p>
        """
        sections = section_chunk_wikipedia(html, "Test")
        ids = [s[0] for s in sections]
        assert len(ids) == len(set(ids))


class TestChunkingConstants:
    def test_parent_larger_than_child(self):
        assert PARENT_CHUNK_SIZE > CHILD_CHUNK_SIZE

    def test_parent_overlap_reasonable(self):
        assert PARENT_CHUNK_OVERLAP < PARENT_CHUNK_SIZE // 2

    def test_child_overlap_reasonable(self):
        assert CHILD_CHUNK_OVERLAP < CHILD_CHUNK_SIZE // 2

    def test_wiki_section_cap_reasonable(self):
        assert WIKI_SECTION_MAX_TOKENS >= 500
        assert WIKI_SECTION_MAX_TOKENS <= 2000
