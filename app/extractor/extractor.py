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
    s = str(val).strip()
    # Strip trailing parenthesised percentage annotations FIRST, e.g. "19(15%)" → "19"
    # These appear in grand-total rows like: "19(15%) 20(15%) 52 (40%)"
    s = re.sub(r'\s*\(\s*\d+\s*%\s*\)', '', s)
    # Also strip bare trailing "%" and whitespace
    s = re.sub(r'[%\s,]', '', s)
    # Strip surrounding parens used for section sub-totals e.g. "(8)"
    s = s.strip('()')
    # If what remains is non-numeric (e.g. "X" placeholder), return 0
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
You are an expert data extraction AI for Philippine PRC (Professional Regulation Commission) Table of Specifications (TOS) documents. These are board exam blueprints listing topics, competency codes, item counts, and Bloom's Taxonomy distributions across multiple subjects — sometimes spanning many pages.

Your output feeds a strict downstream parser. Accuracy and consistency are critical.
NEVER invent, calculate, correct, or guess any numbers or text.

═══════════════════════════════════════════════════════════════
PART 1 — OUTPUT FORMAT
═══════════════════════════════════════════════════════════════

For EACH subject found in the PDF, output EXACTLY this block (no code fences):

ANNEX "<Letter>"
Subject: <Exact Subject Name as printed>
Weight: <N>%

| Topics and Competencies | Weight | No. of Items | Remembering | Understanding | Applying | Analyzing | Evaluating | Creating |
|---|---|---|---|---|---|---|---|---|
| <row> | ... |
| TOTAL | 100% | <N> | <N> | <N> | <N> | <N> | <N> | <N> |

Always exactly 9 columns in that order.

═══════════════════════════════════════════════════════════════
PART 2 — SUBJECT BOUNDARY DETECTION (CRITICAL)
═══════════════════════════════════════════════════════════════

⚠️ EXTRACT EVERY SUBJECT IN THE PDF — NOT JUST THE FIRST ONE.
A TOS PDF typically contains 4 subjects (sometimes more). You MUST output ALL of them.
Do NOT stop after the first subject's grand TOTAL row. Continue processing the rest of
the PDF until you reach the last page. Each subject gets its own complete block.

REAL EXAMPLE — this 12-page PDF contains 4 subjects:
  Pages  1–3:  Developmental Psychology (20%)          ← output block 1
  Pages  4–6:  Psychological Assessment/Psychometrician (40%)  ← output block 2
  Pages  7–9:  Abnormal Psychology (20%)               ← output block 3
  Pages 10–12: Industrial-Organizational Psychology (20%) ← output block 4
ALL FOUR must appear in your output. If you only output 1 or 2, that is WRONG.

A subject block starts ONLY when "Subject:" appears in the PAGE HEADER area of a new page,
accompanied by a "Weight:" line. A subject ends at its grand TOTAL row (100% weight).

NEVER start a new subject block for any of these:
  - Section letters repeating (e.g. a second "B." section header within the same table)
  - Page continuation headers (pages 2, 3 of the same subject repeat the subject name)
  - Section titles that mention common words like "Psychology", "Assessment", "Industrial"
  - Any row inside the data table

A single subject CAN and DOES span multiple pages. When a subject spans pages, the data
table simply continues on the next page — do NOT start a new subject block.

REAL EXAMPLE — "Industrial-Organizational Psychology" spans 3 pages (pages 10, 11, 12):
  Page 10: Subject header + sections A and B (partial)
  Page 11: Continuation — sections B (continued), C, D (no Subject: header on this page)
  Page 12: Continuation — sections D (continued), E (no Subject: header on this page)
  Grand Total appears on page 12 → THAT ends the subject.
  Output: ONE subject block with ALL sections A through E.

═══════════════════════════════════════════════════════════════
PART 3 — ROW CLASSIFICATION
═══════════════════════════════════════════════════════════════

TYPE A — SECTION HEADER:
  Starts with a letter ("A.", "B.", "C.") OR plain number ("1.", "2.") WITHOUT Bloom data.
  Even if the same letter repeats (e.g., two "B." sections due to a PDF numbering error),
  output BOTH as separate section header rows. Do NOT treat the second one as a new subject.
  Example: | B. Human Resource Dev't & Human Resource Mgmt. | 25% | 25 | 0 | 0 | 0 | 0 | 0 | 0 |

TYPE B — DECIMAL COMPETENCY:
  Code like "1.1", "2.3", "3,4" (comma is valid), followed by description text.
  Merge all wrapped lines into one row. Extract all 9 columns.
  Example: | 1.1 Cite major tenets of the psychoanalytic... | | 8 | 8 | 0 | 0 | 0 | 0 | 0 |

TYPE C — NUMBERED COMPETENCY (no decimal):
  Plain "1.", "2." prefix WITH Bloom data in the row.
  Sub-bullets ("a. constructing 2", "b. selecting 1") belong to this row — merge their
  descriptions into Column 1 and SUM their item counts into No. of Items.
  Example: | 1. Ascertain psychometric properties in constructing, selecting, interpreting | | 5 | 5 | 0 | 0 | 0 | 0 | 0 |

TYPE D — SECTION TOTAL:
  Starts with "TOTAL" or "TOTALS" (not 100%). Extract weight, items, and all 6 Bloom values.
  If Bloom values appear on the next line (split layout), merge them into this row.

TYPE E — GRAND TOTAL (subject end marker):
  Patterns: "TOTAL 100%", "TOTALS 100%", "Total (for N items) 100%", "100%", "Grand Total"
  ⚠ SPECIAL CASE — "Total (for N items) 100% 100 30% 40% 30%":
    The trailing "30% 40% 30%" are DIFFICULTY BAND LABELS, not Bloom values.
    Output all 6 Bloom columns as 0. Only extract the total item count (the number after 100%).
    Example: | TOTAL | 100% | 100 | 0 | 0 | 0 | 0 | 0 | 0 |

═══════════════════════════════════════════════════════════════
PART 4 — EDGE CASES
═══════════════════════════════════════════════════════════════

EC-1 PARENTHESISED WEIGHTS/ITEMS: "(5%) (8)" → output "5%" and "8" (no parens).

EC-2 MISSING WEIGHT: If no percentage is printed for a competency, output "" for weight.

EC-3 NON-NUMERIC ITEMS: "X" or "-" instead of a count → output 0.

EC-4 GARBLED SECTION TITLES: Output exactly as printed. Do NOT fix or complete them.
  Example: "6. and Research" → output "6. and Research" verbatim.

EC-5 DIFFICULTY LEVEL HEADER: The visual sub-header "Easy (30%) Moderate (40%) Difficult (30%)"
  is a label spanning the Bloom columns. IGNORE it entirely — it is NOT a data row.

EC-6 MULTI-LINE WRAPPING — INCLUDING CROSS-PAGE BREAKS:
  A competency whose description wraps across lines — even across a page boundary — still
  occupies exactly ONE output row. You MUST merge ALL continuation text into Column 1.
  This is the single most common cause of truncated descriptions. Do NOT stop merging at
  a page boundary. If the text of a competency continues on the next page before any new
  competency code appears, it is still part of the same row.

  REAL EXAMPLE — competency "2.1 Explain the expected developmental tasks..." spans pages:
    Page 2 ends: "2.1 Explain the expected developmental tasks in physical, cognitive,
                  and socio-emotional during"   ← text is incomplete
    Page 3 starts: "childhood, adolescence, and adulthood stages of development."  ← continuation
  Correct output: | 2.1 Explain the expected developmental tasks in physical, cognitive,
                    and socio-emotional during childhood, adolescence, and adulthood
                    stages of development. | 5% | 5 | 0 | 5 | 0 | 0 | 0 | 0 |
  WRONG output:   | 2.1 Explain the expected developmental tasks in physical, cognitive,
                    and socio-emotional during | 5% | 5 | ...  ← TRUNCATED

EC-7 COLUMN HEADER VARIANTS: "No. of items" / "No. of Items" / "No. of Item" / "Nos. of Item"
  all map to column 3 (No. of Items).

EC-8 ANNEX NOTATION VARIANTS: The ANNEX letter may be quoted in different ways:
  ANNEX "A", ANNEX"B", ANNEX ''B" (two apostrophes), ANNEX (A), ANNEX A
  All are valid — extract only the letter A or B.

EC-9 DUPLICATE SECTION LETTERS: Some subjects contain a PDF numbering error where the same
  section letter (e.g. "B.") is used twice. Both are legitimate sections of the SAME subject.
  Output both as separate TYPE A rows within the same subject table.
  REAL EXAMPLE in "Industrial-Organizational Psychology":
    A. Organization Theory
    B. Organizational Structures & Systems     ← first B
    B. Human Resource Dev't & HR Mgmt.        ← second B (PDF error — still same subject!)
    D. Team Dynamics
    E. Organizational Change & Development

EC-10 SECTION SUBTOTALS WITH BLOOM BANDS: Some section TOTAL rows contain difficulty-band
  percentages (30%/40%/30%) instead of Bloom values. Example:
    "TOTALS 100% 130 19(15%) 20(15%) 52(40%) 19(15%) 19(14%) 1(1%)"
  The numbers in parens are percentages of total items. Extract the raw counts only:
  Remembering=19, Understanding=20, Applying=52, Analyzing=19, Evaluating=19, Creating=1.

═══════════════════════════════════════════════════════════════
PART 5 — WHAT TO SKIP
═══════════════════════════════════════════════════════════════

Never emit as table rows:
  - Page headers: "Professional Regulatory Board of Psychology", "Table of Specifications"
  - Board/date metadata: "Board for Psychologists", "as of February 2023", etc.
  - PQF level lines: "PQF Level 6", "PQF Level 7", "(PQF Level 7)"
  - Difficulty band header: "Easy (30%)", "Moderate (40%)", "Difficult (30%)", "Mod (40%)"
  - Bloom taxonomy label row: "Bloom's Taxonomy | Remembering | Understanding | ..."
  - Column header row: "Topics and Competencies | Weight | No. of Items | ..."
  - Intro sentences: "The examinees can perform the following competencies under each topic:"
  - Underscores/dashes used as visual dividers
  - Page continuation of the subject name (same subject name repeated at top of page 2+)

OUTPUT ONLY the plain text subject headers and markdown tables. No preamble, no commentary.
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
    subj_annex  = subj_board = None   # annex/board locked at subject start
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

    def _norm_subj(name: str) -> str:
        """
        Fuzzy-normalize a subject name for deduplication.
        Collapses hyphens, slashes and spaces so variants like
        'Industrial-Organizational', 'Industrial/Organizational', and
        'Industrial Organizational' all map to the same comparison key.
        """
        n = re.sub(r'\*+', '', name)
        n = re.sub(r'[-/]', ' ', n)
        n = re.sub(r'\s+', ' ', n).strip()
        return n.lower()

    def _flush_subject():
        """Commit the current subject and reset all state.

        Guard: skip if the subject has no sections AND no grand_total — this
        means LlamaParse emitted a spurious boundary (subject name repeated as
        a table cell or page-header repeat) with no real data accumulated yet.
        """
        nonlocal annex, board, subj_name, subj_weight
        nonlocal sections, cur_sec, grand_total
        nonlocal col_weight, col_ni, col_bloom, header_found
        nonlocal subj_annex, subj_board
        _save_sec()
        has_content = bool(sections) or grand_total is not None
        # Use the annex/board that were current when this subject STARTED,
        # not whatever LlamaParse may have injected mid-table.
        committed_annex = subj_annex or annex or ''
        committed_board = subj_board or board or ''
        if subj_name and has_content:
            subjects.append({
                'annex':       committed_annex,
                'board':       committed_board,
                'subject':     subj_name,
                'weight':      subj_weight or '',
                'sections':    sections,
                'grand_total': grand_total or {**_zero_bloom(), 'total_items': 0, 'weight': '100%'},
            })
            logger.info(f"Saved subject '{subj_name}' annex={committed_annex} ({len(sections)} sections)")
        elif subj_name:
            logger.warning(
                f"Skipping hollow flush for '{subj_name}' "
                f"(no sections/grand_total — spurious LlamaParse boundary)"
            )
        saved_annex, saved_board = annex, board
        annex = saved_annex
        board = saved_board
        subj_name = subj_weight = grand_total = None
        subj_annex = subj_board = None
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
            # ANNEX marker — match ANNEX A, ANNEX "B", ANNEX ''B", ANNEX(B), etc.
            # NOTE: Do NOT flush subject here. In this PDF all 4 subjects share
            # the same ANNEX B, so ANNEX lines are not subject boundaries.
            # Subject boundaries are detected by the Subject: line below.
            # The ''B" variant is an OCR artefact where " is read as two apostrophes.
            m = re.search(
                r"ANNEX\s*[\"\"«\u201c\u2018\u2019\u201d'`\('']*([AB])",
                stripped, re.I
            )
            if m:
                a = m.group(1).upper()
                annex = a
                board = 'Psychologist' if a == 'A' else 'Psychometrician'

            # Subject: — this is the PRIMARY subject boundary signal.
            # Flush the current subject and start fresh whenever a new Subject:
            # line appears, even if same ANNEX. Use FUZZY comparison (_norm_subj)
            # so 'Industrial-Organizational' == 'Industrial/Organizational' etc.
            m = (re.match(r'\*{0,2}Subject:\*{0,2}\s*\*{0,2}(.+?)\*{0,2}$', stripped, re.I)
                 or re.match(r'Subject:\s*(.+)', stripped, re.I))
            if m:
                new_name = re.sub(r'\*+', '', m.group(1)).strip()
                if _norm_subj(new_name) != _norm_subj(subj_name or ''):
                    saved_annex, saved_board = annex, board
                    _save_comp()
                    _flush_subject()
                    annex, board = saved_annex, saved_board
                    subj_name  = new_name
                    # Lock annex/board to whatever was current at subject start
                    subj_annex = annex
                    subj_board = board

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

        # ── Guard: bare subject-name repetition inside a table cell ───────────
        # LlamaParse sometimes re-emits the current subject name as a standalone
        # table cell (all other columns empty) — e.g. when it encounters a page
        # continuation header mid-parse. Skip these silently; they are pure noise.
        if (c0_clean
                and all(cells[i].strip() == '' for i in range(1, len(cells)))
                and subj_name
                and _norm_subj(c0_clean) == _norm_subj(subj_name)):
            logger.debug(f"Skipping bare subject-name repetition: '{c0_clean}'")
            continue

        # LlamaParse sometimes injects Subject:/Weight: inside a table cell
        m_subj = re.match(r'Subject:\s*(.+)', c0_clean, re.I)
        if m_subj and not any(cells[i].strip() for i in range(1, min(4, len(cells)))):
            new_name = m_subj.group(1).strip()
            if _norm_subj(new_name) != _norm_subj(subj_name or ''):
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
            n = _find_col(cells, 'no. of', 'no of', 'nos. of', 'nos of', 'items'); col_ni = n if n >= 0 else 2
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
            # Guard: if Bloom cells are difficulty-band labels ("30%","40%","30%")
            # rather than item counts, their sum will equal exactly 100 while every
            # individual value is a round percentage (30, 40, 30). Zero them out.
            if sum(bv) == 100 and all(v in (0, 30, 40) for v in bv):
                logger.warning(
                    f"Grand total Bloom values look like difficulty bands {bv}, zeroing"
                )
                bv = [0] * 6
            grand_total = {'weight': '100%', 'total_items': ni, **_bloom_dict(bv)}
            _flush_subject()
            continue

        # ── section TOTAL row ──────────────────────────────────────────────────
        if re.match(r'^TOTALS?$', c0_clean, re.I):
            _save_comp()
            wt_cell = cells[col_weight].strip() if col_weight < len(cells) else ''
            ni = _int(cells[col_ni]) if col_ni < len(cells) else 0
            bv = _bloom_vals(cells)
            bv = _bloom_sanity(bv, ni if ni > 0 else sum(bv))
            if ni == 0:
                ni = sum(bv)

            # Distinguish grand-total from section-total:
            # If the weight cell is "100%" this TOTAL row is the grand total
            # for the subject (LlamaParse sometimes emits it as "TOTAL 100% N ..."
            # without the "100%" in col-0). Treat it as a grand total flush.
            wt_is_100 = re.match(r'^100\s*%?$', re.sub(r'[%\s]', '', wt_cell) + '%')
            if wt_is_100 and ni > 0:
                logger.info(f"Section TOTAL row has 100% weight — treating as grand total (ni={ni})")
                bv_guard = [v for v in bv]
                # Guard: difficulty-band labels (30/40/30) sum to 100 — zero them
                if sum(bv_guard) == 100 and all(v in (0, 30, 40) for v in bv_guard):
                    bv_guard = [0] * 6
                grand_total = {'weight': '100%', 'total_items': ni, **_bloom_dict(bv_guard)}
                _flush_subject()
            elif cur_sec:
                cur_sec['total'] = {
                    'weight': wt_cell,
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
        # Matches: "1.1", "2.3", "3,4" (comma variant), "1.1.1" etc.
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

    _nest_sections(subjects)
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
            # Use page.bbox[1] as the actual top of the page — some PDFs have
            # a non-zero top margin (e.g. bbox[1] ≈ 0.02) which causes a
            # ValueError if we crop from 0 instead of the real top edge.
            page_top    = page.bbox[1]
            page_bottom = page.bbox[3]
            crop_bottom = page_top + (page_bottom - page_top) * 0.20
            header_crop = page.crop((0, page_top, page.width, crop_bottom))
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

    def _norm_subj_geo(name: str) -> str:
        n = re.sub(r'[-/]', ' ', name)
        return re.sub(r'\s+', ' ', n).strip().lower()

    def _flush():
        nonlocal annex, board, subj_name, subj_weight, sections, cur_sec, grand_total
        _ss()
        has_content = bool(sections) or grand_total is not None
        if subj_name and has_content:
            subjects.append({
                'annex':       annex or '',
                'board':       board or '',
                'subject':     subj_name,
                'weight':      subj_weight or '',
                'sections':    sections,
                'grand_total': grand_total or {**_zero_bloom(), 'total_items': 0, 'weight': '100%'},
            })
            logger.info(f"Geometry saved subject '{subj_name}'")
        elif subj_name:
            logger.warning(f"Geometry: skipping hollow flush for '{subj_name}'")
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
            new_name = ph['subject']
            # Only flush if this is genuinely a different subject (fuzzy compare)
            if _norm_subj_geo(new_name) != _norm_subj_geo(subj_name or ''):
                _sc(); _flush()
                subj_name   = new_name
                annex       = ph.get('annex', annex)
                board       = ph.get('board', board)
                subj_weight = ph.get('weight', '')
            else:
                # Same subject continuing on next page — just update weight if missing
                if not subj_weight:
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
            is_grand_geo = (
                re.match(r'^100%$', c0)
                or re.match(r'^TOTAL\s*100%', c0, re.I)
                or re.match(r'^TOTALS?\s*100%', c0, re.I)
                or re.match(r'^Total\s*\(for\s*\d+', c0, re.I)
                or re.match(r'^Grand\s*Total', c0, re.I)
            )
            if is_grand_geo:
                _sc()
                ni = _int(cells[2])
                bv = [_int(cells[j]) for j in range(3, 9)]
                bv = _bloom_sanity_geo(bv, ni)
                # "Total (for N items) 100% 100 30% 40% 30%" — trailing values are
                # difficulty bands (30/40/30), not Bloom counts. Zero them out.
                if sum(bv) == 100 and all(v in (0, 30, 40) for v in bv):
                    logger.warning(f"Geometry: grand total Bloom look like difficulty bands {bv}, zeroing")
                    bv = [0] * 6
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
        prev_bloom_orphan = None  # pure-numeric row with no text, e.g. "9 21 40 22 8 0"
        for top in sorted(line_grp):
            cells = _row_to_cells(line_grp[top], bounds)
            c0 = cells[0].strip()
            if not c0 and all(c == '' for c in cells[1:]):
                continue

            # Orphan pure-numeric row: no text in col 0, only numbers in cols 1-8.
            # Seen in IO Psych where Bloom totals appear on the line BEFORE the
            # "Total (for 100 items)" grand-total row.
            is_orphan_bloom = (
                not c0
                and any(cells[j].strip() for j in range(1, 9))
                and all(re.fullmatch(r'[\d%().\s]*', cells[j]) for j in range(1, 9))
            )
            if is_orphan_bloom:
                prev_bloom_orphan = cells[:]
                continue

            # If this is the grand total row and we have orphan Bloom values waiting,
            # fill in any zero Bloom slots with values from the orphan row.
            is_grand_row = bool(
                re.match(r'^100%$', c0)
                or re.match(r'^TOTALS?\s*100%', c0, re.I)
                or re.match(r'^Total\s*\(for\s*\d+', c0, re.I)
                or re.match(r'^Grand\s*Total', c0, re.I)
            )
            if is_grand_row and prev_bloom_orphan is not None:
                for j in range(3, 9):
                    if not cells[j].strip() or _int(cells[j]) == 0:
                        cells[j] = prev_bloom_orphan[j]
                prev_bloom_orphan = None

            if prev is not None and c0 and all(c == '' for c in cells[1:]) and any(prev[j] for j in range(1, 9)):
                prev[0] += ' ' + c0
                continue
            if prev:
                _proc(prev)
            prev = cells[:]
            prev_bloom_orphan = None
        if prev:
            _proc(prev)

    _sc(); _flush()
    _nest_sections(subjects)
    logger.info(f"parse_pdf_geometry: {len(subjects)} subjects extracted")
    return {'subjects': subjects}


# ─────────────────────────────────────────────────────────────────────────────
# Hierarchy post-processor
# ─────────────────────────────────────────────────────────────────────────────

def _nest_sections(subjects: list) -> list:
    """
    Convert the flat sections list produced by both parsers into a two-level
    hierarchy that the frontend can render without custom logic:

    BEFORE (flat):
      sections: [
        {"title": "A. Perspectives on Nature and Nurture", "competencies": [...]},
        {"title": "B. Research Methods...",                "competencies": []},
        {"title": "1. Ethics in Conducting Research",      "competencies": [...]},
        {"title": "2. Research Methods in Dev Psych",      "competencies": [...]},
        {"title": "C. Developmental Theories",             "competencies": []},
        {"title": "1. Theories of development...",         "competencies": [...]},
      ]

    AFTER (nested):
      sections: [
        {"title": "A. Perspectives on Nature and Nurture",
         "level": "letter", "subsections": [], "competencies": [...]},
        {"title": "B. Research Methods...",
         "level": "letter",
         "subsections": [
           {"title": "1. Ethics in Conducting Research",
            "level": "number", "subsections": [], "competencies": [...]},
           {"title": "2. Research Methods in Dev Psych",
            "level": "number", "subsections": [], "competencies": [...]},
         ],
         "competencies": []},
        {"title": "C. Developmental Theories",
         "level": "letter",
         "subsections": [
           {"title": "1. Theories of development...",
            "level": "number", "subsections": [], "competencies": [...]},
         ],
         "competencies": []},
      ]

    Rules:
    - A section whose title starts with a LETTER prefix (A., B., …, F.) is a
      top-level (letter) section.
    - A section whose title starts with a NUMBER prefix (1., 2., …) is a
      subsection and belongs to the most-recently-seen letter section.
    - If a number-prefixed section has no preceding letter section it is
      promoted to the top level (level="number") so nothing is lost.
    - The existing "total" and "grand_total" keys are preserved unchanged.
    - A new "level" key ("letter" | "number") is added to every section.
    - A new "subsections" key (list) is added to every section.
    """
    _letter_re = re.compile(r'^[A-F]\.\s+\S', re.I)
    _number_re = re.compile(r'^\d{1,2}\.\s+\S')

    for subj in subjects:
        flat = subj.get('sections', [])
        nested   = []
        cur_letter = None   # the most recent letter-level section dict

        for sec in flat:
            title = sec.get('title', '')
            is_letter = bool(_letter_re.match(title))
            is_number = bool(_number_re.match(title)) and not is_letter

            if is_letter:
                sec['level']       = 'letter'
                sec['subsections'] = []
                nested.append(sec)
                cur_letter = sec

            elif is_number:
                sec['level']       = 'number'
                sec['subsections'] = []
                if cur_letter is not None:
                    cur_letter['subsections'].append(sec)
                else:
                    # No parent letter section yet — promote to top level
                    nested.append(sec)

            else:
                # Unclassifiable title (empty, truncated, etc.) — keep as-is
                sec.setdefault('level', 'letter')
                sec.setdefault('subsections', [])
                nested.append(sec)
                cur_letter = sec

        subj['sections'] = nested

    return subjects


# ─────────────────────────────────────────────────────────────────────────────
# Quality check
# ─────────────────────────────────────────────────────────────────────────────

def _count_expected_subjects(pdf_path: str) -> int:
    """
    Count how many distinct Subject: headers appear in the page header area.
    Uses the same safe bbox logic as _extract_page_headers to avoid crop errors.
    Deduplicates fuzzy-normalised names so variants like
    'Industrial-Organizational' and 'Industrial/Organizational' count as one.
    """
    seen = set()
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                page_top    = page.bbox[1]
                page_bottom = page.bbox[3]
                # Use only the top 20% — same as _extract_page_headers
                crop_bottom = page_top + (page_bottom - page_top) * 0.20
                hdr = page.crop((0, page_top, page.width, crop_bottom))
                hdr_text = hdr.extract_text() or ''
                m = re.search(r'^Subject:\s*(.+)$', hdr_text, re.I | re.M)
                if m:
                    raw = m.group(1).strip()
                    # Fuzzy-normalise: collapse -/  and whitespace, lowercase
                    norm = re.sub(r'[-/]', ' ', raw)
                    norm = re.sub(r'\s+', ' ', norm).strip().lower()
                    seen.add(norm)
    except Exception as e:
        logger.warning(f"_count_expected_subjects failed: {e}")
    return max(1, len(seen))


def _result_is_good(data: dict, expected_subjects: int = 1) -> bool:
    """
    Quality check for extracted TOS data.

    Fails if:
    - No subjects found
    - Fewer subjects than expected (LlamaParse returned partial output)
    - Fewer than 5 competencies total
    - Fewer than 10% of competencies have any bloom data

    Works with BOTH the old flat section structure and the new nested structure
    (sections can have subsections after _nest_sections() runs).
    """
    subjs = data.get('subjects', [])
    if not subjs:
        return False

    if len(subjs) < expected_subjects:
        logger.warning(
            f"Quality check failed: got {len(subjs)} subjects, "
            f"expected {expected_subjects} — partial LlamaParse output"
        )
        return False

    def _collect_comps(sections):
        """Collect competencies from sections + their subsections."""
        result = []
        for sec in sections:
            result.extend(sec.get('competencies', []))
            result.extend(_collect_comps(sec.get('subsections', [])))
        return result

    comps = [c for s in subjs for c in _collect_comps(s.get('sections', []))]
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

    # Count how many subjects this PDF is expected to contain
    # so we can detect LlamaParse partial-output failures
    expected_subjects = _count_expected_subjects(pdf_path)
    logger.info(f"Expected subjects in PDF: {expected_subjects}")

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
                    if not _result_is_good(data, expected_subjects):
                        logger.warning(
                            f"LlamaParse quality insufficient "
                            f"(got {len(data.get('subjects',[]))} of {expected_subjects} subjects) "
                            f"— geometry fallback"
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
                if not _result_is_good(data, expected_subjects):
                    logger.warning(
                        f"Geometry also weak "
                        f"(got {len(data.get('subjects',[]))} of {expected_subjects} subjects)"
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