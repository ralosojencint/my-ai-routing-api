import ast
import pathlib
import py_compile
import re
from datetime import date, datetime
from email.utils import parsedate_to_datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

ROOT = pathlib.Path(__file__).resolve().parents[1]
APP = ROOT / 'streamlit_app.py'

QUERY = (
    'Find 3 current AI developments today. Use exactly one source for each development. '
    'For each development, explain what happened, the organizations involved, why it matters, '
    'and the publication date. Use only evidence published today if possible. Do not count '
    'multiple articles about the same underlying event as separate developments. For every '
    'factual claim that comes from a source, cite the specific source immediately after that claim. '
    'At the end, provide a Sources section containing only those 3 sources.'
)


def load_functions():
    tree = ast.parse(APP.read_text(encoding='utf-8'))
    needed = {
        'clean_text', 'clean_ai_response', 'normalize_url', 'source_domain', 'source_date',
        'source_combined', 'is_relevant_ai_source', 'event_tokens', '_event_title_tokens',
        'same_event', 'source_outlet_key', 'select_distinct_sources',
        'requested_development_count', 'requires_exact_today', 'requested_research_date',
        'source_grounded_summary', '_source_sentences', '_publisher_name', '_candidate_organizations',
        '_source_significance', 'validate_research_output', 'render_exact_research_output',
        'should_research', 'detect_route', 'route_label', 'is_forex_query',
    }
    constants = {
        'RESEARCH_AI_TERMS', 'EVENT_TERMS', 'EVENT_ANCHOR_TERMS', 'PRIMARY_DOMAINS',
        'SECONDARY_TRUSTED_DOMAINS', 'ROUTE_RESEARCH', 'ROUTE_FOREX', 'ROUTE_DATA',
        'ROUTE_DOCUMENTS', 'ROUTE_VISION', 'ROUTE_GENERAL'
    }
    ns = {
        're': re,
        'st': type(
            'ST',
            (),
            {'session_state': type('SS', (), {'datasets': [], 'documents': []})()}
        )(),
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


def test_production_syntax():
    py_compile.compile(str(APP), doraise=True)
    assert APP.stat().st_size > 50000


def test_research_contract_and_dates():
    ns = load_functions()
    assert ns['requested_development_count'](QUERY, default=5) == 3
    assert ns['requires_exact_today'](QUERY)
    assert ns['source_date'](
        {'published_date': '2026-09-03T10:30:00Z'}
    ) == date(2026, 9, 3)
    assert ns['source_date'](
        {'published_date': 'Wed, 03 Sep 2026 10:30:00 GMT'}
    ) == date(2026, 9, 3)
    assert ns['source_date'](
        {'published_date': 'September 3, 2026'}
    ) == date(2026, 9, 3)


def test_url_and_event_deduplication():
    ns = load_functions()
    assert ns['normalize_url'](
        'https://www.example.com/story/amp?utm_source=x&x=1'
    ) == ns['normalize_url'](
        'https://example.com/story?x=1'
    )

    a = source(
        'Apple launches Mac Studio with new AI chips',
        'https://example.com/a',
        'Apple launched Mac Studio featuring new chips designed for AI workloads.',
        '2026-09-03'
    )
    b = source(
        'Apple announces Mac Studio with AI-focused chips',
        'https://example.net/b',
        'Apple announced Mac Studio with chips focused on AI workloads.',
        '2026-09-03'
    )
    c = source(
        'Anthropic launches a new enterprise AI model',
        'https://example.org/c',
        'Anthropic launched a new enterprise AI model for business customers.',
        '2026-09-03'
    )

    assert ns['same_event'](a, b)
    assert len(ns['select_distinct_sources']([a, b, c], limit=3)) == 2


def test_relevance_and_noise_gates():
    ns = load_functions()

    good = source(
        'Apple launches Mac Studio with new AI chips',
        'https://example.com/a',
        'Apple launched Mac Studio featuring new chips designed for AI workloads.',
        '2026-09-03'
    )
    old = dict(good, published_date='2026-09-02')
    noise = source(
        'AI activists protest OpenAI data center expansion',
        'https://example.com/p',
        'Activists protested an AI infrastructure project.',
        '2026-09-03'
    )

    assert ns['is_relevant_ai_source'](good, date(2026, 9, 3))
    assert not ns['is_relevant_ai_source'](
        old,
        date(2026, 9, 3),
        target_date=date(2026, 9, 3)
    )
    assert not ns['is_relevant_ai_source'](noise, date(2026, 9, 3))
    assert ns['should_research'](
        'What are the latest AI developments today?'
    )
    assert not ns['should_research']('What is 2 + 2?')


def test_output_contract_and_rejections():
    ns = load_functions()

    a = source(
        'Apple launches Mac Studio with new AI chips',
        'https://example.com/a',
        'Apple launched Mac Studio featuring new chips designed for AI workloads.',
        '2026-09-03'
    )
    c = source(
        'Anthropic launches a new enterprise AI model',
        'https://example.org/c',
        'Anthropic launched a new enterprise AI model for business customers.',
        '2026-09-03'
    )

    selected = [a, c]
    fallback = ns['render_exact_research_output'](QUERY, selected)

    assert re.search(r'(?m)^1\. ', fallback)
    assert re.search(r'(?m)^2\. ', fallback)
    assert '[Source 1]' in fallback and '[Source 2]' in fallback
    assert '### Sources' in fallback
    assert ns['validate_research_output'](fallback, QUERY, selected)

    assert not ns['validate_research_output'](
        fallback.replace('2. **', '1. **', 1),
        QUERY,
        selected
    )

    assert not ns['validate_research_output'](
        fallback.replace('[Source 2]', '[Source 9]'),
        QUERY,
        selected
    )

    assert not ns['validate_research_output'](
        fallback + '\n3. Extra — https://example.com/extra',
        QUERY,
        selected
    )

    assert not ns['validate_research_output'](
        fallback + '\n\n### Sources\n1. Extra — https://example.com/extra',
        QUERY,
        selected
    )

    missing = re.sub(
        r'^- Why it matters:.*$',
        '',
        fallback,
        flags=re.M
    )
    assert not ns['validate_research_output'](
        missing,
        QUERY,
        selected
    )

    insufficient = ns['render_exact_research_output'](QUERY, [c])
    assert 'Only 1 independently verified development(s) were available' in insufficient
    assert ns['validate_research_output'](
        insufficient,
        QUERY,
        [c]
    )


def test_router_contracts():
    ns = load_functions()
    assert str(
        ns['detect_route']('Find the latest AI developments today')
    ).lower() != 'general'

    assert 'forex' in str(
        ns['detect_route'](
            'Show me high-impact USD events on Forex Factory'
        )
    ).lower()


def test_phase3_safeguards_present():
    text = APP.read_text(encoding='utf-8')

    for fragment in (
        'Evidence-integrity research output contract passed',
        'validate_research_output(draft, query, sources)',
        'deterministic fallback',
        'allowed_dates={today}',
        'if exact_today or target_date==today:',
    ):
        assert fragment in text, f'Missing production safeguard: {fragment}'
