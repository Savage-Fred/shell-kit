#!/usr/bin/env python3
"""List assignment names without executing files or displaying their values.

Only explicit files are read. No expansion, sourcing, evaluation, or recursion.
The parser is deliberately conservative: this is an inventory, not a shell
validator. An unsupported here-document stops inspection of the rest of a file.
Unclosed quotes, substitutions, or parentheses suppress the unfinished record.
Only assignments at the beginning of a statement are inventoried. Additional
space-separated assignments and arbitrary shell commands are warning records.
"""
import argparse
import json
import os
import re
import stat
import sys
from collections import defaultdict

IDENTIFIER = r'[A-Za-z_][A-Za-z0-9_]*'
ASSIGNMENT = re.compile(r'^\s*(?:export[ \t]+)?(' + IDENTIFIER + r')[ \t]*=')


def split_statements(source):
    """Return (statement, start line) pairs and a count of lexical warnings."""
    records, buf, stack = [], [], []
    line = start = 1
    i = 0
    warnings = 0
    word_start = True
    while i < len(source):
        c = source[i]
        top = stack[-1] if stack else None
        if top == "'":
            buf.append(c)
            if c == "'":
                stack.pop()
            line += c == '\n'
            i += 1
            continue
        if c == '\\':
            if i + 1 == len(source):
                warnings += 1
                return records, warnings
            buf.extend(source[i:i + 2])
            line += source[i + 1] == '\n'
            i += 2
            word_start = False
            continue
        if top in ('"', '`') and c == top:
            stack.pop()
            buf.append(c)
            i += 1
            word_start = False
            continue
        if c == '$' and source[i:i + 2] in ('$(', '${'):
            stack.append(source[i:i + 2])
            buf.extend(source[i:i + 2])
            i += 2
            word_start = False
            continue
        if c == '`' and top != '`':
            stack.append('`')
        elif top != '"' and c in ("'", '"'):
            stack.append(c)
        elif top not in ('"', '`'):
            if source[i:i + 2] == '<<':
                # A here-document body can resemble assignments. Suppress all
                # remaining input rather than risk misidentifying its contents.
                return records, warnings + 1
            if c == '#' and word_start:
                end = source.find('\n', i)
                if end < 0:
                    i = len(source)
                    break
                i = end
                continue
            if c == '(':
                stack.append('(')
            elif c == ')' and top in ('(', '$('):
                stack.pop()
            elif c == '}' and top == '${':
                stack.pop()
            elif c in (')', '}') and not stack:
                # Flag malformed standalone delimiters without exposing text.
                warnings += 1
        if c in ('\n', ';') and not stack:
            if ''.join(buf).strip():
                records.append((''.join(buf), start))
            buf = []
            line += c == '\n'
            start = line
            word_start = True
        else:
            if not buf and c.isspace():
                start = line
            buf.append(c)
            line += c == '\n'
            word_start = c.isspace()
        i += 1
    if stack:
        warnings += 1
    elif ''.join(buf).strip():
        records.append((''.join(buf), start))
    return records, warnings


def top_level_words(value):
    """Count shell-like value words, retaining no words in the result.

    shlex is intentionally not used: substitutions have different lexical rules.
    Space boundaries are counted only outside quotes and substitutions.
    """
    stack = []
    count = 0
    in_word = False
    i = 0
    while i < len(value):
        c = value[i]
        top = stack[-1] if stack else None
        if not stack and c.isspace():
            in_word = False
            i += 1
            continue
        if not in_word:
            count += 1
            in_word = True
        if top == "'":
            if c == "'":
                stack.pop()
        elif c == '\\':
            i += 1
        elif top in ('"', '`') and c == top:
            stack.pop()
        elif value[i:i + 2] in ('$(', '${'):
            stack.append(value[i:i + 2])
            i += 1
        elif c == '`':
            stack.append('`')
        elif top != '"' and c in ("'", '"'):
            stack.append(c)
        elif top not in ('"', '`'):
            if c == '(':
                stack.append('(')
            elif c == ')' and top in ('(', '$('):
                stack.pop()
            elif c == '}' and top == '${':
                stack.pop()
            elif not stack and c in '|&<>':
                return 2
        i += 1
    return count


def inspect_text(source):
    records, warnings = split_statements(source)
    names = []
    for statement, start in records:
        match = ASSIGNMENT.match(statement)
        if not match:
            warnings += 1
            continue
        value = statement[match.end():]
        if top_level_words(value) > 1:
            # Do not partially inventory compound or otherwise ambiguous forms.
            warnings += 1
            continue
        names.append({'name': match.group(1), 'line': start})
    occurrences = defaultdict(list)
    for item in names:
        occurrences[item['name']].append(item['line'])
    duplicates = [dict(name=name, lines=lines, count=len(lines))
                  for name, lines in sorted(occurrences.items()) if len(lines) > 1]
    return {'names': names, 'duplicates': duplicates,
            'parse_warning_count': warnings}


def audit_file(path):
    # Do not echo filenames: a filename itself could contain sensitive text.
    try:
        # Nonblocking open prevents an explicitly supplied FIFO from hanging.
        descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode):
                return {'error': 'not_regular_file'}
            with os.fdopen(os.dup(descriptor), 'r', encoding='utf-8') as stream:
                source = stream.read()
        finally:
            os.close(descriptor)
    except (OSError, UnicodeError):
        return {'error': 'unreadable_file'}
    result = inspect_text(source)
    result['permissions'] = format(stat.S_IMODE(metadata.st_mode), '04o')
    return result


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv == ['help']:
        argv = ['--help']
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--json', action='store_true', help='emit structured names-only JSON')
    parser.add_argument('paths', nargs='+', help='explicit files to inspect; never sourced or evaluated')
    args = parser.parse_args(argv)
    results = [audit_file(path) for path in args.paths]
    if args.json:
        print(json.dumps({'files': results}, indent=2))
    else:
        for index, result in enumerate(results, 1):
            print('File', index)
            if 'error' in result:
                print('  Error:', result['error'])
                continue
            print('  Permissions:', result['permissions'])
            for entry in result['names']:
                print('  {name} (line {line})'.format(**entry))
            for entry in result['duplicates']:
                print('  Duplicate {name}: count {count}, lines {lines}'.format(**entry))
            print('  Parse warnings:', result['parse_warning_count'])
    return int(any('error' in result for result in results))


if __name__ == '__main__':
    raise SystemExit(main())
