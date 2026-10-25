"""Strict physical-LF JSONL framing; Unicode separators are record content.

Adapt the frozen core in memory. Never edit its source or discard broken rows.
"""
import json
from pathlib import Path
import sys
from types import ModuleType


class JSONLDecodeError(json.JSONDecodeError):
    def __init__(self, error, source, physical_line):
        self.source = str(source)
        self.physical_line = physical_line
        super().__init__(
            f'{self.source}: physical JSONL line {physical_line}, column {error.colno}: {error.msg}',
            error.doc, error.pos,
        )


def _parse(lines, source):
    result = []
    for number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            result.append(json.loads(line))
        except json.JSONDecodeError as error:
            raise JSONLDecodeError(error, source, number) from error
    return result


def loads_jsonl(data, source='<JSONL>'):
    """Decode an in-memory member without str.splitlines()' Unicode boundaries."""
    if isinstance(data, bytes):
        data = data.decode('utf-8-sig')
    elif data.startswith('\ufeff'):
        data = data[1:]
    return _parse(data.split('\n'), source)


def read_jsonl(path):
    # newline='\n' also accepts CRLF through JSON whitespace. U+0085/U+2028/
    # U+2029 inside strings remain unchanged. Invalid/truncated JSON still fails.
    with Path(path).open(encoding='utf-8-sig', newline='\n') as stream:
        return _parse(stream, path)


def install():
    """Cover fresh imports and already-bound `from io_utils import jsonl` aliases."""
    import io_utils
    previous = io_utils.jsonl
    if previous is read_jsonl:
        return
    for module in list(sys.modules.values()):
        if isinstance(module, ModuleType):
            namespace = vars(module)
            if namespace.get('jsonl') is previous:
                namespace['jsonl'] = read_jsonl
    io_utils.jsonl = read_jsonl
