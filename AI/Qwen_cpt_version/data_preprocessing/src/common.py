"""Conservative text normalization, geometry, PII filtering and JSONL I/O."""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from pathlib import Path


def digest(value: str | bytes) -> str:
    return hashlib.sha256(value.encode('utf-8') if isinstance(value, str) else value).hexdigest()


def normalize(text: str, code: bool = False) -> str:
    text = unicodedata.normalize('NFC', text).replace('\u00a0', ' ')
    text = ''.join(c for c in text if c in '\n\t' or unicodedata.category(c) not in ('Cc', 'Cf'))
    if code:
        return '\n'.join(line.rstrip() for line in text.splitlines()).strip('\n')
    return '\n'.join(re.sub(r'[ \t]+', ' ', line).strip() for line in text.splitlines()).strip()


EMAIL = re.compile(r'(?<![\w.])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}(?![\w.])')
# A phone needs a contact label: arbitrary algorithm numbers must survive.
PHONE = re.compile(r'(?i)((?:điện thoại|đt|tel|phone|mobile|liên hệ)\s*[:：]?\s*)(\+?\d[\d .()-]{7,}\d)')
ID_NUMBER = re.compile(r'(?i)((?:CCCD|CMND|căn cước|mã số sinh viên|MSSV)\s*[:：]?\s*)([A-Z0-9-]{6,})')


def redact(text: str) -> tuple[str, list[dict]]:
    events = []
    for pattern, kind, group in [(EMAIL, 'email', 0), (PHONE, 'phone', 2), (ID_NUMBER, 'identifier', 2)]:
        def repl(match):
            value = match.group(group)
            events.append({'type': kind, 'value_sha256': digest(value)})
            return match.group(1) + '[REDACTED_' + kind.upper() + ']' if group else '[REDACTED_EMAIL]'
        text = pattern.sub(repl, text)
    return text, events


def dump_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(path)


def write_jsonl(path: Path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    with tmp.open('w', encoding='utf-8', newline='\n') as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + '\n')
    tmp.replace(path)


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(s) for s in path.read_text(encoding='utf-8').splitlines() if s.strip()]


def box_union(boxes):
    boxes = list(boxes)
    return [min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes)]


def area(box):
    return max(0, box[2]-box[0]) * max(0, box[3]-box[1])


def overlap(a, b):
    return area([max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])])


def latex_check(text: str) -> dict:
    """Syntax smoke check only; never claims mathematical correctness."""
    import latex2mathml.converter
    stack = []
    error = None
    for i, c in enumerate(text):
        if i and text[i-1] == '\\':
            continue
        if c == '{':
            stack.append(c)
        elif c == '}':
            if not stack:
                error = 'unbalanced_braces'
                break
            stack.pop()
    if stack:
        error = 'unbalanced_braces'
    if not text.strip():
        error = 'empty_formula'
    if error is None:
        try:
            latex2mathml.converter.convert(text)
        except Exception as exc:
            error = type(exc).__name__
    return {'syntax_valid': error is None, 'error': error, 'semantic_verified': False}
