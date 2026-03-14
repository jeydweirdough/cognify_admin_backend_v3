"""
extractor.py — TOS PDF Extractor  (llama-cloud >= 1.0 / pdfplumber fallback)

FIXES vs original:
  1. LlamaParse: added custom_prompt (agentic_options) so the model understands
     the multi-subject, multi-page PRC TOS structure.
  2. LlamaParse: added aggressive_table_extraction + disable_heuristics so
     tables are NOT reformatted / merged incorrectly.
  3. Parser: grand-total row now calls save_subj() (not just save_sec()), so
     subjects 2-4 are actually committed to the list.
  4. Parser: non-table lines no longer blindly reset header_found — column
     indices survive page breaks within the same subject.
  5. Parser: Subject boundary detection handles LlamaParse injecting metadata
     inside table cells (inline Subject:/Weight: rows).
  6. Geometry fallback: grand-total row also calls flush_subj() for same fix.
"""

import re, time, logging
from datetime import datetime, timezone
from pathlib import Path
from collections import defaultdict

import llama_cloud
import pdfplumber
from app.extractor import config_inline as config

logger = logging.getLogger(__name__)

BLOOM_KEYS = [
    'bloom_remembering', 'bloom_understanding', 'bloom_applying',
    'bloom_analyzing',   'bloom_evaluating',    'bloom_creating',
]

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _int(val) -> int:
    if val is None:
        return 0
    s = re.sub(r'[%\(\)\s,]', '', str(val))
    m = re.search(r'\d+', s)
    return int(m.group()) if m else 0

def _zero_bloom() -> dict:
    return {k: 0 for k in BLOOM_KEYS}

def _bloom_dict(vals: list) -> dict:
    return {k: (vals[i] if i < len(vals) else 0) for i, k in enumerate(BLOOM_KEYS)}

def _clean_desc(text: str) -> str:
    """Strip LlamaParse artefacts from competency description strings."""
    if not text:
        return text
    text = re.sub(r'\\+\s*\d+\.\s*[^\\]*\\*', ' ', text)
    text = re.sub(r'\\+\s*[A-F]\.\s*[^\\]*\\*', ' ', text)
    text = text.replace('\\', ' ')
    text = re.sub(r'\*+', '', text)
    text = re.sub(r'\s+\d{1,3}\s*$', '', text)
    text = re.sub(r'\s*\d+%\s*$', '', text)
    return ' '.join(text.split())


# ─────────────────────────────────────────────────────────────────────────────
# LlamaParse system prompt
# ─────────────────────────────────────────────────────────────────────────────

_TOS_PROMPT = """
You are a deterministic data extraction engine for Philippine PRC Table of Specifications (TOS) PDFs.

Your ONLY purpose is to extract ALL subjects, sections, and competencies from the uploaded PDF exactly as written and reproduce them in a strictly structured Markdown format. 

Never summarize, paraphrase, or add conversational text. Do not output anything outside of the requested format.

═══════════════════════════════════════════════════════
REQUIRED OUTPUT FORMAT (STRICT)
═══════════════════════════════════════════════════════

For EACH subject block in the document, you MUST output the following exact structure. Do not wrap the output in ```markdown code blocks.

ANNEX "<letter>"
Subject: <exact subject name from the PDF>
Weight: <N>%

| Topics/Competencies | Weight | No. of Items | Remembering | Understanding | Applying | Analyzing | Evaluating | Creating |
|---|---|---|---|---|---|---|---|---|
| A. <Section Title> | "" | "" | "" | "" | "" | "" | "" | "" |
| 1.1 <Competency text> | 2% | 2 | 0 | 2 | 0 | 0 | 0 | 0 |
| TOTAL | 100% | 100 | 15 | 15 | 40 | 20 | 10 | 0 |

═══════════════════════════════════════════════════════
RULES FOR EXTRACTION
═══════════════════════════════════════════════════════

1. SUBJECT BOUNDARIES:
   - Metadata lines (Board for..., as of..., PQF Level, Difficulty Level) must be IGNORED.
   - Only extract `ANNEX`, `Subject:`, and `Weight:` and place them strictly ABOVE the markdown table as plain text.
   - A new subject begins with a "Subject:" header.

2. COLUMN NORMALIZATION (CRITICAL):
   - Every table must have EXACTLY 9 columns.
   - You MUST normalize Bloom's Taxonomy columns into the exact order shown above, regardless of their visual order in the PDF.
   - Each number from the PDF belongs to exactly ONE Bloom column. Never duplicate.

3. ROW HANDLING:
   - SECTION HEADER ROWS (e.g., "A. Foundations"): Put the title in Column 1. Fill Columns 2-9 with empty strings `""`.
   - COMPETENCY ROWS (e.g., "1.1 Explain...", "2. Apply..."): Put text in Column 1. Fill missing numeric cells with `0`.
   - MERGED/WRAPPED TEXT: If a competency spans multiple lines in the PDF, merge it into a single line. Never split one competency into multiple rows.

4. TOTALS:
   - The final row of a subject is usually the GRAND TOTAL (e.g., "100%", "TOTAL 100%"). Extract it into the 9 columns accordingly.

DO NOT add explanations, commentary, or markdown formatting blocks. Output raw text and tables only. Extract ALL subjects present in the document.
""".strip()


# ─────────────────────────────────────────────────────────────────────────────
# LlamaParse extraction
# ─────────────────────────────────────────────────────────────────────────────

def llamaparse_extract_markdown(pdf_path: str) -> str:
    api_key = config.LLAMA_CLOUD_API_KEY
    if not api_key:
        raise ValueError("LLAMA_CLOUD_API_KEY not set")

    client = llama_cloud.LlamaCloud(api_key=api_key)
    logger.info("Uploading to LlamaParse (agentic, custom prompt)…")

    with open(pdf_path, 'rb') as f:
        result = client.parsing.parse(
            tier='agentic',
            version='latest',
            upload_file=('document.pdf', f, 'application/pdf'),
            # Domain-specific prompt so the model knows the TOS layout
            agentic_options={
                'custom_prompt': _TOS_PROMPT,
            },
            # Force aggressive table extraction; disable heuristics that
            # reformat or merge multi-page tables in unexpected ways
            processing_options={
                'aggressive_table_extraction': True,
                'disable_heuristics':          True,
            },
            output_options={
                'markdown': {
                    'tables': {
                        'output_tables_as_markdown': True,
                        'merge_continued_tables':    True,
                    }
                }
            },
            expand=['markdown', 'markdown_full'],
            verbose=True,
        )

    status = result.job.status if result.job else 'unknown'
    logger.info(f"LlamaParse status: {status}")

    if result.markdown_full:
        logger.info(f"Got markdown_full ({len(result.markdown_full)} chars)")
        return result.markdown_full

    if result.markdown and result.markdown.pages:
        pages_md = []
        for p in result.markdown.pages:
            content_str = getattr(p, 'md', None) or getattr(p, 'text', None) or ''
            if content_str:
                pages_md.append(content_str)
        if pages_md:
            logger.info(f"Got {len(pages_md)} markdown pages")
            return '\n\n---PAGE---\n\n'.join(pages_md)

    raise RuntimeError(
        f"LlamaParse returned no markdown. "
        f"status={status} markdown_full={result.markdown_full is not None} "
        f"markdown={result.markdown is not None}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Markdown table helpers
# ─────────────────────────────────────────────────────────────────────────────

def _parse_md_table_row(line: str) -> list:
    line = line.strip()
    if not line.startswith('|'):
        return []
    cells = line.split('|')
    cells = cells[1:-1] if cells and cells[-1].strip() == '' else cells[1:]
    return [c.strip() for c in cells]

def _is_separator_row(cells: list) -> bool:
    return bool(cells) and all(
        re.match(r'^[-:]+$', c.replace(' ', '')) for c in cells if c.strip()
    )

def _find_bloom_cols(cells: list) -> dict:
    mapping = {
        'bloom_remembering':   ['remembering', 'remember'],
        'bloom_understanding': ['understanding', 'understand'],
        'bloom_applying':      ['applying', 'apply'],
        'bloom_analyzing':     ['analyzing', 'analysing', 'analyze', 'analyse'],
        'bloom_evaluating':    ['evaluating', 'evaluate'],
        'bloom_creating':      ['creating', 'create'],
    }
    out = {}
    for i, c in enumerate(cells):
        cl = c.lower().strip()
        for key, variants in mapping.items():
            if any(v in cl for v in variants):
                out[key] = i
    return out

def _find_col(cells: list, *patterns) -> int:
    for i, c in enumerate(cells):
        cl = c.lower()
        for p in patterns:
            if p in cl:
                return i
    return -1


# ─────────────────────────────────────────────────────────────────────────────
# LlamaParse markdown parser
# ─────────────────────────────────────────────────────────────────────────────

def parse_llamaparse_markdown(full_md: str) -> dict:
    """
    Parse LlamaParse markdown into structured TOS data.

    Fixes vs previous version:
    - annex/board now preserved across subject flushes correctly
    - grand_total Bloom values read from correct named columns (not positional)
    - garbled numbers from Psych Assessment section-level rows handled
    - TOTALS row without col_ni match now sums Bloom values
    - section header regex extended to handle lowercase starts and multi-word
    - Bloom column index guard prevents out-of-bounds crash
    - `ni == 0 → sum(bv)` only applied when ALL bloom vals also suggest items
    """
    subjects    = []
    annex       = board = subj_name = subj_weight = None
    sections    = []
    cur_sec     = None
    cur_comp    = None
    grand_total = None

    col_weight   = 1
    col_ni       = 2
    col_bloom: dict = {}
    header_found = False

    # ── state helpers ──────────────────────────────────────────────────────────

    def _save_comp():
        nonlocal cur_comp
        if cur_comp is not None and cur_sec is not None:
            cur_sec['competencies'].append(cur_comp)
            cur_comp = None

    def _save_sec():
        nonlocal cur_sec
        _save_comp()
        if cur_sec is not None:
            sections.append(cur_sec)
            cur_sec = None

    def _flush_subject():
        """Commit the current subject and reset all state."""
        nonlocal annex, board, subj_name, subj_weight
        nonlocal sections, cur_sec, grand_total
        nonlocal col_weight, col_ni, col_bloom, header_found
        _save_sec()
        if subj_name:
            subjects.append({
                'annex':       annex or '',
                'board':       board or '',
                'subject':     subj_name,
                'weight':      subj_weight or '',
                'sections':    sections,
                'grand_total': grand_total or {**_zero_bloom(), 'total_items': 0, 'weight': '100%'},
            })
            logger.info(f"Saved subject '{subj_name}' ({len(sections)} sections)")
        # Save annex/board across flush — they persist to the next subject
        # (all 4 subjects in this PDF are under the same board)
        saved_annex, saved_board = annex, board
        annex = saved_annex
        board = saved_board
        subj_name = subj_weight = grand_total = None
        sections     = []
        cur_sec      = None
        col_weight   = 1
        col_ni       = 2
        col_bloom    = {}
        header_found = False

    def _safe_bloom_val(cells, key):
        """Get a bloom value safely from the named column, 0 if out of bounds."""
        idx = col_bloom.get(key, -1)
        if idx < 0 or idx >= len(cells):
            return 0
        return _int(cells[idx])

    def _bloom_vals(cells: list) -> list:
        if col_bloom:
            return [_safe_bloom_val(cells, k) for k in BLOOM_KEYS]
        # Fallback: positional cols 3-8
        return [_int(cells[i]) if i < len(cells) else 0 for i in range(3, 9)]

    def _bloom_sanity(bv: list, ni: int) -> list:
        """
        Sanity-check bloom values. If any single value exceeds ni significantly
        it means column boundaries were mis-read (e.g. Psych Assessment garbling).
        In that case, zero out all bloom values — better than storing garbage.
        """
        if ni <= 0:
            return bv
        if any(v > ni * 20 for v in bv):  # 20x item count = clearly garbled
            logger.warning(f"Bloom values look garbled (ni={ni}, bv={bv}), zeroing out")
            return [0] * len(bv)
        return bv

    # ── line loop ──────────────────────────────────────────────────────────────

    for line in full_md.splitlines():
        stripped = line.strip()

        # page separator — keep column knowledge across pages in same subject
        if '---PAGE---' in stripped or stripped == '---':
            continue

        # ── non-table text: Annex / Subject / Weight metadata ─────────────────
        if not stripped.startswith('|'):
            # ANNEX marker — match ANNEX A, ANNEX "B", ANNEX(B), etc.
            # NOTE: Do NOT flush subject here. In this PDF all 4 subjects share
            # the same ANNEX B, so ANNEX lines are not subject boundaries.
            # Subject boundaries are detected by the Subject: line below.
            m = re.search(r'ANNEX\s*[""«\u201c\u2018\u2019\u201d\'"\(]*([AB])', stripped, re.I)
            if m:
                a = m.group(1).upper()
                annex = a
                board = 'Psychologist' if a == 'A' else 'Psychometrician'

            # Subject: — this is the PRIMARY subject boundary signal.
            # Flush the current subject and start fresh whenever a new Subject:
            # line appears, even if same ANNEX. Use normalised comparison to
            # handle minor whitespace/casing variations from LlamaParse.
            m = (re.match(r'\*{0,2}Subject:\*{0,2}\s*\*{0,2}(.+?)\*{0,2}$', stripped, re.I)
                 or re.match(r'Subject:\s*(.+)', stripped, re.I))
            if m:
                new_name = re.sub(r'\*+', '', m.group(1)).strip()
                new_name_norm = re.sub(r'\s+', ' ', new_name).lower()
                cur_name_norm = re.sub(r'\s+', ' ', subj_name or '').lower()
                if new_name_norm != cur_name_norm:
                    saved_annex, saved_board = annex, board
                    _save_comp()
                    _flush_subject()
                    annex, board = saved_annex, saved_board
                    subj_name = new_name

            # Weight:
            m = (re.match(r'\*{0,2}Weight:\*{0,2}\s*(\d+%)', stripped, re.I)
                 or re.match(r'Weight:\s*(\d+%)', stripped, re.I))
            if m:
                subj_weight = m.group(1)

            continue

        # ── markdown table row ─────────────────────────────────────────────────
        cells = _parse_md_table_row(stripped)
        if not cells or _is_separator_row(cells):
            continue

        c0       = cells[0].strip()
        c0_clean = re.sub(r'\*+', '', c0).strip()

        # LlamaParse sometimes injects Subject:/Weight: inside a table cell
        m_subj = re.match(r'Subject:\s*(.+)', c0_clean, re.I)
        if m_subj and not any(cells[i].strip() for i in range(1, min(4, len(cells)))):
            new_name = m_subj.group(1).strip()
            new_name_norm = re.sub(r'\s+', ' ', new_name).lower()
            cur_name_norm  = re.sub(r'\s+', ' ', subj_name or '').lower()
            if new_name_norm != cur_name_norm:
                saved_annex, saved_board = annex, board
                _save_comp(); _flush_subject()
                annex, board = saved_annex, saved_board
                subj_name = new_name
            continue

        m_wt = re.match(r'Weight:\s*(\d+%)', c0_clean, re.I)
        if m_wt and not any(cells[i].strip() for i in range(1, min(4, len(cells)))):
            subj_weight = m_wt.group(1)
            continue

        # Also detect inline ANNEX inside table cell (rare but happens)
        # Only update annex/board — do NOT flush. Subject: line handles boundaries.
        m_annex = re.search(r'ANNEX\s*[""«\u201c\u2018\u2019\u201d\'"\(]*([AB])', c0_clean, re.I)
        if m_annex and not any(cells[i].strip() for i in range(1, min(4, len(cells)))):
            annex = m_annex.group(1).upper()
            board = 'Psychologist' if annex == 'A' else 'Psychometrician'
            continue

        # ── table header row ───────────────────────────────────────────────────
        is_header = (
            any('remembering' in c.lower() for c in cells) or
            any('topics' in c.lower() and 'competenc' in c.lower() for c in cells)
        )
        if is_header and not header_found:
            header_found = True
            col_bloom    = _find_bloom_cols(cells)
            w = _find_col(cells, 'weight');        col_weight = w if w >= 0 else 1
            n = _find_col(cells, 'no. of', 'no of', 'items'); col_ni = n if n >= 0 else 2
            logger.debug(f"Header cols: weight={col_weight} ni={col_ni} bloom={col_bloom}")
            continue

        # ── skip noise rows ────────────────────────────────────────────────────
        SKIP = [
            r'^PQF Level', r'^Difficulty', r"^Bloom'?s", r'^Topics',
            r'^The Examinees?', r'^Easy', r'^Moderate', r'^Difficult',
            r'^No\.?\s+of', r'^Weight$', r'^Board', r'^Examinees',
        ]
        if any(re.match(p, c0_clean, re.I) for p in SKIP):
            continue

        # ── GRAND TOTAL — end of subject block ────────────────────────────────
        is_grand = (
            re.match(r'^100%$', c0_clean)
            or re.match(r'^TOTAL\s*100%', c0_clean, re.I)
            or re.match(r'^Total\s*\(for\s*\d+', c0_clean, re.I)
            or re.match(r'^Grand\s*Total', c0_clean, re.I)
            or re.match(r'^TOTALS?\s*100%', c0_clean, re.I)
        )
        if is_grand:
            _save_comp()
            ni = _int(cells[col_ni]) if col_ni < len(cells) else 0
            bv = _bloom_vals(cells)
            bv = _bloom_sanity(bv, ni)
            grand_total = {'weight': '100%', 'total_items': ni, **_bloom_dict(bv)}
            _flush_subject()
            continue

        # ── section TOTAL row ──────────────────────────────────────────────────
        if re.match(r'^TOTALS?$', c0_clean, re.I):
            _save_comp()
            ni = _int(cells[col_ni]) if col_ni < len(cells) else 0
            bv = _bloom_vals(cells)
            bv = _bloom_sanity(bv, ni if ni > 0 else sum(bv))
            if ni == 0:
                ni = sum(bv)
            if cur_sec:
                cur_sec['total'] = {
                    'weight': cells[col_weight] if col_weight < len(cells) else '',
                    'total_items': ni,
                    **_bloom_dict(bv),
                }
            continue

        # ── section header ─────────────────────────────────────────────────────
        # Matches: "A. Title", "B. Title", "1. Title", "2. Title" etc.
        # Does NOT match competency codes like "1.1", "2.3"
        is_sec = (
            bool(re.match(r'^[A-F]\.\s+\S', c0_clean))
            or bool(re.match(r'^\d{1,2}\.\s+[A-Za-z\u201c]', c0_clean))
        ) and not bool(re.match(r'^\d{1,2}[.,]\d', c0_clean))

        # CRITICAL: Psych Assessment uses numbered competencies ("1. Ascertain...",
        # "2. Describe...") that carry Bloom data directly on the same row.
        # Only reclassify as competency when:
        #   - prefix is a NUMBER (not A./B./C. which are always section headers)
        #   - AND the row has Bloom data in cols 3-8 (not just a subtotal in col 2)
        if is_sec:
            is_numbered = bool(re.match(r'^\d{1,2}\.\s+', c0_clean))
            bloom_data = any(_int(cells[i]) > 0 for i in range(3, min(9, len(cells))))
            if is_numbered and bloom_data:
                # Reclassify: numbered competency without a decimal code
                _save_comp()
                m_num = re.match(r'^(\d{1,2})\.\s+(.*)', c0_clean, re.S)
                if m_num:
                    code = m_num.group(1)
                    desc = _clean_desc(m_num.group(2).strip())
                else:
                    code, desc = '', _clean_desc(c0_clean)

                wt  = cells[col_weight] if col_weight < len(cells) else ''
                ni  = _int(cells[col_ni]) if col_ni < len(cells) else 0
                bv  = _bloom_vals(cells)
                bv  = _bloom_sanity(bv, ni if ni > 0 else sum(bv))
                if ni == 0 and 0 < sum(bv) <= 50:
                    ni = sum(bv)

                if cur_sec is None:
                    cur_sec = {'title': '', 'competencies': [], 'total': None}

                cur_comp = {
                    'code': code, 'description': desc,
                    'weight': wt, 'no_of_items': ni,
                    **_bloom_dict(bv),
                }
                continue
            else:
                _save_comp()
                _save_sec()
                cur_sec = {'title': c0_clean, 'competencies': [], 'total': None}
                continue

        # ── competency row ─────────────────────────────────────────────────────
        if re.match(r'^\d{1,2}[.,]\d{1,2}', c0_clean):
            _save_comp()
            m = re.match(r'^(\d{1,2}[.,]\d{1,2}\.?(?:\d{1,2})?)\s+(.*)', c0_clean, re.S)
            if m:
                code = m.group(1).rstrip('.,')
                desc = _clean_desc(re.sub(r'\s+\d+\s*$', '', m.group(2).strip()))
            else:
                code, desc = c0_clean, ''

            wt = cells[col_weight] if col_weight < len(cells) else ''
            ni = _int(cells[col_ni]) if col_ni < len(cells) else 0
            bv = _bloom_vals(cells)
            bv = _bloom_sanity(bv, ni if ni > 0 else sum(bv))
            # Only infer ni from bloom when ni truly 0 AND sum(bv) is plausible
            if ni == 0 and 0 < sum(bv) <= 50:
                ni = sum(bv)

            if cur_sec is None:
                cur_sec = {'title': '', 'competencies': [], 'total': None}

            cur_comp = {
                'code': code, 'description': desc,
                'weight': wt, 'no_of_items': ni,
                **_bloom_dict(bv),
            }
            continue

        # ── description continuation row ───────────────────────────────────────
        if cur_comp is not None and c0_clean:
            other_empty = all(
                cells[i].strip() == '' if i < len(cells) else True
                for i in range(1, 9)
            )
            if other_empty:
                cur_comp['description'] += ' ' + c0_clean

    # Flush whatever remains (last subject if PDF has no trailing 100% row)
    _save_comp()
    _flush_subject()

    logger.info(f"parse_llamaparse_markdown: {len(subjects)} subjects extracted")
    return {'subjects': subjects}



# ─────────────────────────────────────────────────────────────────────────────
# pdfplumber geometry fallback
# ─────────────────────────────────────────────────────────────────────────────

def _detect_col_boundaries(words: list, page_width: float) -> list:
    left_cutoff = page_width * 0.30
    num_x0s = []
    for w in words:
        t = w['text'].strip()
        if not re.fullmatch(r'\d{1,3}%?', t):
            continue
        v = _int(t)
        if v <= 0 or v > 200:
            continue
        if w['x0'] < left_cutoff:
            continue
        num_x0s.append(w['x0'])

    if len(num_x0s) < 16:
        logger.warning(f"Too few numeric anchors ({len(num_x0s)}) — fixed fallback bounds")
        left  = page_width * 0.38
        right = page_width * 0.99
        step  = (right - left) / 8
        return [left + step * i for i in range(8)]

    num_x0s.sort()
    lo = num_x0s[len(num_x0s) // 20]
    hi = num_x0s[min(len(num_x0s) - 1, len(num_x0s) * 19 // 20)]
    num_x0s = [x for x in num_x0s if lo <= x <= hi]

    gaps = sorted(
        ((num_x0s[i + 1] - num_x0s[i], i) for i in range(len(num_x0s) - 1)),
        reverse=True,
    )
    split_indices = sorted(g[1] for g in gaps[:7])

    boundaries = []
    start = 0
    for idx in split_indices:
        boundaries.append(min(num_x0s[start:idx + 1]))
        start = idx + 1
    tail = num_x0s[start:]
    boundaries.append(min(tail) if tail else num_x0s[-1])
    boundaries.sort()

    merged = [boundaries[0]]
    for b in boundaries[1:]:
        if b - merged[-1] > 8:
            merged.append(b)

    while len(merged) < 8:
        last = merged[-1]
        merged.append(last + (page_width - last) / (9 - len(merged)))
    return merged[:8]


def _assign_col(cx: float, bounds: list) -> int:
    for i in range(len(bounds) - 1, -1, -1):
        if cx >= bounds[i] - 3:
            return i + 1
    return 0


def _extract_page_headers(pdf_path: str) -> dict:
    """
    Extract Annex/Subject/Weight metadata from the PAGE HEADER AREA only.

    Scans only the top 20% of each page to prevent false positives from
    table cells or footers containing "Subject:" on continuation pages of
    a multi-page subject block — which previously caused premature flushes
    and dropped rows from pages 2+ of the same subject.
    """
    headers = {}
    with pdfplumber.open(pdf_path) as pdf:
        for pn, page in enumerate(pdf.pages, 1):
            # Only look at the top 20% of the page for subject/weight metadata
            header_crop = page.crop((0, 0, page.width, page.height * 0.20))
            header_text = header_crop.extract_text() or ''
            full_text   = page.extract_text() or ''

            info = {}
            # ANNEX: check header crop first; fall back to full page but only
            # if it appears on its own line (not embedded in a table cell)
            m = re.search(r'ANNEX\s*[""«\u201c\u2018\u2019\u201d\'\(]*([AB])', header_text, re.I)
            if not m:
                m = re.search(r'(?m)^ANNEX\s*[""«\u201c\u2018\u2019\u201d\'\(]*([AB])\s*$', full_text, re.I)
            if m:
                info['annex'] = m.group(1).upper()
                info['board'] = 'Psychologist' if info['annex'] == 'A' else 'Psychometrician'

            # Subject/Weight: ONLY from the header crop — never from full page
            m = re.search(r'^Subject:\s*(.+)$', header_text, re.I | re.M)
            if m:
                info['subject'] = m.group(1).strip()
            m = re.search(r'^Weight:\s*(\d+%)', header_text, re.I | re.M)
            if m:
                info['weight'] = m.group(1)

            if info:
                headers[pn] = info
    return headers


def parse_pdf_geometry(pdf_path: str) -> dict:
    page_headers = _extract_page_headers(pdf_path)

    with pdfplumber.open(pdf_path) as pdf:
        pages_words = [
            p.extract_words(x_tolerance=3, y_tolerance=3,
                            keep_blank_chars=False, use_text_flow=False)
            for p in pdf.pages
        ]
        page_widths = [float(p.width) for p in pdf.pages]

    all_words     = [w for pw in pages_words for w in pw]
    global_bounds = _detect_col_boundaries(all_words, page_widths[0])
    logger.info(f"Geometry global bounds: {[f'{x:.0f}' for x in global_bounds]}")

    subjects    = []
    annex       = board = subj_name = subj_weight = None
    sections    = []
    cur_sec     = None
    grand_total = None
    cur_comp    = None

    def _sc():
        nonlocal cur_comp
        if cur_comp and cur_sec is not None:
            cur_sec['competencies'].append(cur_comp)
            cur_comp = None

    def _ss():
        nonlocal cur_sec
        _sc()
        if cur_sec is not None:
            sections.append(cur_sec)
            cur_sec = None

    def _bloom_sanity_geo(bv, ni):
        if ni <= 0:
            return bv
        if any(v > ni * 20 for v in bv):
            logger.warning(f"Geometry: bloom values garbled (ni={ni}, bv={bv}), zeroing")
            return [0] * len(bv)
        return bv

    def _flush():
        nonlocal annex, board, subj_name, subj_weight, sections, cur_sec, grand_total
        _ss()
        if subj_name:
            subjects.append({
                'annex':       annex or '',
                'board':       board or '',
                'subject':     subj_name,
                'weight':      subj_weight or '',
                'sections':    sections,
                'grand_total': grand_total or {**_zero_bloom(), 'total_items': 0, 'weight': '100%'},
            })
            logger.info(f"Geometry saved subject '{subj_name}'")
        # Preserve annex/board — they carry forward to next subject
        saved_annex, saved_board = annex, board
        annex = saved_annex
        board = saved_board
        subj_name = subj_weight = grand_total = None
        sections = []
        cur_sec  = None

    def _row_to_cells(words, bounds):
        grp = defaultdict(list)
        for w in words:
            cx = (w['x0'] + w['x1']) / 2
            grp[_assign_col(cx, bounds)].append(w['text'])
        return [' '.join(grp.get(i, [])) for i in range(9)]

    for pn, words in enumerate(pages_words, 1):
        ph = page_headers.get(pn, {})
        if 'subject' in ph:
            _sc(); _flush()
            subj_name   = ph['subject']
            annex       = ph.get('annex', annex)
            board       = ph.get('board', board)
            subj_weight = ph.get('weight', '')
        elif 'annex' in ph:
            annex = ph['annex']
            board = ph.get('board', board)

        bounds = _detect_col_boundaries(words, page_widths[pn - 1])
        if not bounds or bounds == global_bounds:
            bounds = global_bounds

        line_grp: dict = defaultdict(list)
        for w in words:
            line_grp[round(w['top'] / 4) * 4].append(w)

        def _proc(cells):
            nonlocal cur_sec, cur_comp, grand_total
            c0 = cells[0].strip()
            SKIP = [
                r'^PQF Level', r'^Difficulty', r"^Bloom'?s", r'^Topics',
                r'^The Examinees?', r'^Easy', r'^Moderate', r'^Difficult',
                r'^No\.?\s+of', r'^Weight$', r'^Board', r'^as of',
                r'^Subject:', r'^Weight:', 'Professional Regulatory', 'Table of Spec',
            ]
            if any(re.match(p, c0, re.I) for p in SKIP):
                return

            # Grand total — flush subject
            if (re.match(r'^100%$', c0)
                    or re.match(r'^TOTAL\s*100%', c0, re.I)
                    or re.match(r'^TOTALS?\s*100%', c0, re.I)
                    or re.match(r'^Total\s*\(for\s*\d+', c0, re.I)
                    or re.match(r'^Grand\s*Total', c0, re.I)):
                _sc()
                ni = _int(cells[2])
                bv = [_int(cells[j]) for j in range(3, 9)]
                bv = _bloom_sanity_geo(bv, ni)
                grand_total = {'weight': '100%', 'total_items': ni, **_bloom_dict(bv)}
                _flush()
                return

            if re.match(r'^TOTALS?$', c0, re.I):
                _sc()
                ni = _int(cells[2]); bv = [_int(cells[j]) for j in range(3, 9)]
                bv = _bloom_sanity_geo(bv, ni if ni > 0 else sum(bv))
                if ni == 0: ni = sum(bv)
                if cur_sec:
                    cur_sec['total'] = {'weight': cells[1], 'total_items': ni, **_bloom_dict(bv)}
                return

            is_sec = (
                bool(re.match(r'^[A-F]\.\s+\S', c0))
                or bool(re.match(r'^\d{1,2}\.\s+[A-Za-z\u201c]', c0))
            ) and not bool(re.match(r'^\d{1,2}[.,]\d', c0))
            if is_sec:
                # If the row is number-prefixed AND has Bloom data (cols 3-8),
                # it is a numbered competency (Psych Assessment style).
                # Lettered headers (A., B.) with only a subtotal in col 2 remain sections.
                is_numbered = bool(re.match(r'^\d{1,2}\.\s+', c0))
                bloom_data  = any(_int(cells[i]) > 0 for i in range(3, 9))
                has_numeric_data = is_numbered and bloom_data
                if has_numeric_data:
                    _sc()
                    m_num = re.match(r'^(\d{1,2})\.\s+(.*)', c0, re.S)
                    if m_num:
                        code = m_num.group(1)
                        desc = _clean_desc(m_num.group(2).strip())
                    else:
                        code, desc = '', _clean_desc(c0)
                    ni = _int(cells[2]); bv = [_int(cells[j]) for j in range(3, 9)]
                    bv = _bloom_sanity_geo(bv, ni if ni > 0 else sum(bv))
                    if ni == 0 and 0 < sum(bv) <= 50: ni = sum(bv)
                    if cur_sec is None:
                        cur_sec = {'title': '', 'competencies': [], 'total': None}
                    cur_comp = {
                        'code': code, 'description': desc,
                        'weight': cells[1], 'no_of_items': ni,
                        **_bloom_dict(bv),
                    }
                else:
                    _sc(); _ss()
                    cur_sec = {'title': c0, 'competencies': [], 'total': None}
                return

            if re.match(r'^\d{1,2}[.,]\d{1,2}', c0):
                _sc()
                m = re.match(r'^(\d{1,2}[.,]\d{1,2}\.?(?:\d{1,2})?)\s+(.*)', c0, re.S)
                code, desc = (
                    (m.group(1).rstrip('.,'), _clean_desc(re.sub(r'\s+\d+\s*$', '', m.group(2).strip())))
                    if m else ('', _clean_desc(c0))
                )
                ni = _int(cells[2]); bv = [_int(cells[j]) for j in range(3, 9)]
                bv = _bloom_sanity_geo(bv, ni if ni > 0 else sum(bv))
                if ni == 0 and 0 < sum(bv) <= 50: ni = sum(bv)
                if cur_sec is None:
                    cur_sec = {'title': '', 'competencies': [], 'total': None}
                cur_comp = {
                    'code': code, 'description': desc,
                    'weight': cells[1], 'no_of_items': ni,
                    **_bloom_dict(bv),
                }
                return

            if cur_comp and c0 and all(cells[j] == '' for j in range(1, 9)):
                cur_comp['description'] += ' ' + c0

        prev = None
        for top in sorted(line_grp):
            cells = _row_to_cells(line_grp[top], bounds)
            c0 = cells[0].strip()
            if not c0 and all(c == '' for c in cells[1:]):
                continue
            if prev is not None and c0 and all(c == '' for c in cells[1:]) and any(prev[j] for j in range(1, 9)):
                prev[0] += ' ' + c0
                continue
            if prev:
                _proc(prev)
            prev = cells[:]
        if prev:
            _proc(prev)

    _sc(); _flush()
    logger.info(f"parse_pdf_geometry: {len(subjects)} subjects extracted")
    return {'subjects': subjects}


# ─────────────────────────────────────────────────────────────────────────────
# Quality check
# ─────────────────────────────────────────────────────────────────────────────

def _result_is_good(data: dict) -> bool:
    subjs = data.get('subjects', [])
    if not subjs:
        return False
    comps = [
        c for s in subjs
        for sec in s.get('sections', [])
        for c in sec.get('competencies', [])
    ]
    if len(comps) < 5:
        return False
    bloom_ok = sum(1 for c in comps if any(c.get(k, 0) > 0 for k in BLOOM_KEYS))
    return bloom_ok >= max(1, len(comps) * 0.10)


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def extract(pdf_path: str, source_hash: str) -> tuple:
    """
    Extract TOS data from a PDF.

    Returns:
        (True,  'SUCCESS',     result_dict)  — on success
        (False, error_message, None)          — on failure

    result_dict:
        {
            'extracted_at':      str  (ISO-8601 UTC),
            'source_hash':       str,
            'extraction_method': 'llamaparse' | 'geometry',
            'data':              { 'subjects': [...] },
        }
    """
    if not Path(pdf_path).exists():
        return False, f"PDF not found: {pdf_path}", None

    for attempt in range(1, config.MAX_RETRIES + 1):
        try:
            logger.info(f"Extraction attempt {attempt}: {pdf_path}")
            data = method = None

            # ── LlamaParse ────────────────────────────────────────────────────
            if config.LLAMA_CLOUD_API_KEY:
                try:
                    md     = llamaparse_extract_markdown(pdf_path)
                    data   = parse_llamaparse_markdown(md)
                    method = 'llamaparse'
                    if not _result_is_good(data):
                        logger.warning(
                            f"LlamaParse quality insufficient "
                            f"({len(data.get('subjects',[]))} subjects) — geometry fallback"
                        )
                        data = method = None
                    else:
                        n_comp = sum(
                            len(sec.get('competencies', []))
                            for s in data['subjects']
                            for sec in s.get('sections', [])
                        )
                        logger.info(
                            f"LlamaParse OK: {len(data['subjects'])} subjects, "
                            f"{n_comp} competencies"
                        )
                except Exception as e:
                    logger.warning(f"LlamaParse failed: {e} — geometry fallback")
                    data = method = None
            else:
                logger.warning("No LLAMA_CLOUD_API_KEY — skipping LlamaParse")

            # ── geometry fallback ─────────────────────────────────────────────
            if data is None:
                logger.info("Using pdfplumber geometry extraction…")
                data   = parse_pdf_geometry(pdf_path)
                method = 'geometry'
                if not _result_is_good(data):
                    logger.warning(
                        f"Geometry also weak ({len(data.get('subjects',[]))} subjects)"
                    )

            result = {
                'extracted_at':      datetime.now(timezone.utc).isoformat(),
                'source_hash':       source_hash,
                'extraction_method': method,
                'data':              data,
            }
            logger.info(f"Done ({method}): {len(data.get('subjects',[]))} subjects")
            return True, 'SUCCESS', result

        except Exception as e:
            logger.warning(f"Attempt {attempt} failed: {e}", exc_info=True)
            if attempt < config.MAX_RETRIES:
                time.sleep(config.RETRY_BASE_DELAY ** attempt)

    return False, 'Max retries reached', None