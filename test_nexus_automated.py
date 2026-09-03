import ast
import pathlib
import py_compile
import re
from datetime import date, datetime
from email.utils import parsedate_to_datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# Change only this path when the production NEXUS file changes.
APP = pathlib.Path(__file__).with_name('streamlit_app(20260903-025803).py')

QUERY = (
    'Find 3 current AI developments today. Use exactly one source for each development. '
    'For each development, explain what happened, the organizations involved, why it matters, '
    'and the publication date. Use only evidence published today if possible. Do not count '
    'multiple articles about the same underlying event as separate developments. For every '
    'factual claim that comes from a source, cite the specific source immediately after that claim. '
    'At the end, provide a Sources section containing only those 3 sources.'
)


def load_functions():
    """Load pure NEXUS functions without starting Streamlit or making API calls."""
    tree = ast.parse(APP.read_text(encoding='utf-8'))
    needed = {
        'clean_text', 'clean_ai_response', 'normalize_url', 'source_domain', 'source_date',
        'source_combined', 'is_relevant_ai_source', 'event_tokens', '_event_title_tokens',
        'same_event', 'source_outlet_key', 'select_distinct_sources',
        'requested_development_count', 'requires_exact_today', 'requested_research_date',
        'source_grounded_summary', '_source_sentences', '_publisher_name', '_candidate_organizations', '_source_significance',
        'validate_research_output', 'render_exact_research_output', 'should_research',
        'detect_route', 'route_label', 'is_forex_query',
    }
    constants = {'RESEARCH_AI_TERMS', 'EVENT_TERMS', 'EVENT_ANCHOR_TERMS', 'PRIMARY_DOMAINS', 'SECONDARY_TRUSTED_DOMAINS', 'ROUTE_RESEARCH', 'ROUTE_FOREX', 'ROUTE_DATA', 'ROUTE_DOCUMENTS', 'ROUTE_VISION', 'ROUTE_GENERAL'}
    ns = {
        're': re,
        'st': type('ST', (), {'session_state': type('SS', (), {'datasets': [], 'documents': []})()})(),
        'date': date,
        'datetime': datetime,
        'parsedate_to_datetime': parsedate_to_datetime,
        'urlsplit': urlsplit,
        'urlunsplit': urlunsplit,
        'parse_qsl': parse_qsl,
        'urlencode': urlencode,
    }
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in needed:
            exec(compile(ast.Module([node], []), '<nexus-test>', 'exec'), ns)
        elif isinstance(node, ast.Assign):
            names = {x.id for x in node.targets if isinstance(x, ast.Name)}
            if names & constants:
                exec(compile(ast.Module([node], []), '<nexus-test>', 'exec'), ns)
    return ns


def source(title, url, content, published):
    return {
        'title': title,
        'url': url,
        'content': content,
        'published_date': published,
    }


def main():
    assert APP.exists(), f'Missing production file: {APP}'
    py_compile.compile(str(APP), doraise=True)
    ns = load_functions()

    # 1. Core syntax / load gate.
    assert APP.stat().st_size > 50000

    # 2. Research count + exact-today contract.
    assert ns['requested_development_count'](QUERY, default=5) == 3
    assert ns['requires_exact_today'](QUERY)

    # 3. ISO-8601 regression: T + Z must parse correctly.
    assert ns['source_date']({'published_date': '2026-09-03T10:30:00Z'}) == date(2026, 9, 3)

    # 4. Other common date formats remain supported.
    assert ns['source_date']({'published_date': 'Wed, 03 Sep 2026 10:30:00 GMT'}) == date(2026, 9, 3)
    assert ns['source_date']({'published_date': 'September 3, 2026'}) == date(2026, 9, 3)

    # 5. URL canonicalization removes tracking/AMP noise.
    a = 'https://www.example.com/story/amp?utm_source=x&x=1'
    b = 'https://example.com/story?x=1'
    assert ns['normalize_url'](a) == ns['normalize_url'](b)

    # 6. Same underlying event must deduplicate.
    apple1 = source(
        'Apple launches Mac Studio with new AI chips',
        'https://example.com/apple1',
        'Apple launched Mac Studio featuring new chips designed for AI workloads.',
        '2026-09-03',
    )
    apple2 = source(
        'Apple announces Mac Studio with AI-focused chips',
        'https://example.net/apple2',
        'Apple announced Mac Studio with chips focused on AI workloads.',
        '2026-09-03',
    )
    other = source(
        'Anthropic launches a new enterprise AI model',
        'https://example.org/anthropic',
        'Anthropic launched a new enterprise AI model for business customers.',
        '2026-09-03',
    )
    assert ns['same_event'](apple1, apple2)
    selected = ns['select_distinct_sources']([apple1, apple2, other], limit=3)
    assert len(selected) == 2

    # 7. Relevant AI event passes the precision gate.
    assert ns['is_relevant_ai_source'](apple1, date(2026, 9, 3))

    # 8. Yesterday is not today's exact evidence.
    yesterday = dict(apple1, published_date='2026-09-02')
    assert ns['source_date'](yesterday) == date(2026, 9, 2)
    assert ns['is_relevant_ai_source'](yesterday, date(2026, 9, 3), target_date=date(2026, 9, 3)) is False

    # 9. Activism/noise rejection.
    protest = source(
        'AI activists protest OpenAI data center expansion',
        'https://example.com/protest',
        'Activists protested an AI infrastructure project.',
        '2026-09-03',
    )
    assert not ns['is_relevant_ai_source'](protest, date(2026, 9, 3))

    # 10. Research intent detection.
    assert ns['should_research']('What are the latest AI developments today?')
    assert not ns['should_research']('What is 2 + 2?')

    # 11. Deterministic fallback has correct numbered structure and one source per item.
    fallback = ns['render_exact_research_output'](QUERY, selected)
    assert fallback
    assert re.search(r'(?m)^1\. ', fallback)
    assert re.search(r'(?m)^2\. ', fallback)
    assert '[Source 1]' in fallback
    assert '[Source 2]' in fallback
    assert '### Sources' in fallback
    assert ns['validate_research_output'](fallback, QUERY, selected)

    # 12. Duplicate numbering is rejected.
    bad_numbering = fallback.replace('2. **', '1. **', 1)
    assert not ns['validate_research_output'](bad_numbering, QUERY, selected)

    # 13. Invalid source marker is rejected.
    invalid_marker = fallback.replace('[Source 2]', '[Source 9]')
    assert not ns['validate_research_output'](invalid_marker, QUERY, selected)

    # 14. Extra Sources entry is rejected.
    extra = fallback + '\n3. Extra — https://example.com/extra'
    assert not ns['validate_research_output'](extra, QUERY, selected)

    # 15. Duplicate Sources section is rejected.
    duplicate_section = fallback + '\n\n### Sources\n1. Extra — https://example.com/extra'
    assert not ns['validate_research_output'](duplicate_section, QUERY, selected)

    # 16. Missing required evidence field is rejected.
    missing_field = re.sub(r'^- Why it matters:.*$', '', fallback, flags=re.M)
    assert not ns['validate_research_output'](missing_field, QUERY, selected)

    # 17. Insufficient evidence is allowed only when explicitly acknowledged.
    insufficient = ns['render_exact_research_output'](QUERY, [other])
    assert 'Only 1 independently verified development(s) were available' in insufficient
    assert ns['validate_research_output'](insufficient, QUERY, [other])

    # 18. Router must classify current-news research away from General.
    route = ns['detect_route']('Find the latest AI developments today')
    assert str(route).lower() != 'general'

    # 19. Router must classify Forex separately.
    forex_route = ns['detect_route']('Show me high-impact USD events on Forex Factory')
    assert 'forex' in str(forex_route).lower()

    # 20. Production code contains the Phase 3 boundary and deterministic fallback.
    text = APP.read_text(encoding='utf-8')
    required_fragments = [
        'Evidence-integrity research output contract passed',
        'validate_research_output(draft, query, sources)',
        'deterministic fallback',
        'allowed_dates={today}',
        'if exact_today or target_date==today:',
    ]
    for fragment in required_fragments:
        assert fragment in text, f'Missing production safeguard: {fragment}'

    print('20/20 PASS — NEXUS automated Phase 3 regression suite')


if __name__ == '__main__':
    main()
