from __future__ import annotations

from app.services.agent_tools import _context_terms


def test_context_terms_extracts_balanced_quotes() -> None:
    terms = _context_terms('客户「安测委托A」 项目"年度检测项目A" 有哪些报告')

    assert '安测委托A' in terms
    assert '年度检测项目A' in terms


def test_context_terms_handles_unclosed_quote_input() -> None:
    text = '"' + '『a' * 20000

    assert _context_terms(text) == []
