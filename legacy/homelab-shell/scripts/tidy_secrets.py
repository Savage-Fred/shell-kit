#!/usr/bin/env python3
"""Conservatively sort literal shell assignments without displaying their values.

Dry run is the default. --apply writes atomically after comparing current bytes.
Only contiguous, complete, single-line literal assignments are sorted. Comments,
blank lines, expansions, commands, and unsupported syntax are barriers. Repeated
names retain their ordering; only adjacent byte-identical assignments are removed.
Files are never sourced, evaluated, or expanded. Output contains fixed categories
and counts only. -h, --help, and help display this documentation.
On macOS, ACLs and extended attributes are preserved and verified, except
com.apple.provenance: macOS can regenerate this protected attribute on a new
inode and silently ignore attempts to restore it. Source conflict checks still
compare every original attribute, including provenance, without exceptions.
"""
import argparse
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile

from audit_secrets import split_statements

NAME = r'[A-Za-z_][A-Za-z0-9_]*'
# Exclude every expansion/operator/escape and all trailing comments. Whitespace
# around '=' is not accepted: these are shell assignments, not dotenv records.
LITERAL = re.compile(r'^[ \t]*(?:export[ \t]+)?(' + NAME + r')=(?:'
                     r"'[^'\r\n]*'|"
                     r'"[^"$`\\!\r\n]*"|'
                     r'[A-Za-z0-9_./:@%+,=\-]*'
                     r')[ \t]*(?:\r?\n)?$')


def transform(source):
    """Return new text and value-free counts; preserve RHS and line bytes."""
    pieces = source.split('\n')
    lines = [piece + '\n' for piece in pieces[:-1]]
    if pieces[-1]:
        lines.append(pieces[-1])
    records, warnings = split_statements(source)
    safe_lines = {line for record, line in records
                  if '\n' not in record and '\r' not in record}
    # CRLF records retain a trailing carriage return in the lexical record.
    safe_lines.update(line for record, line in records
                      if '\n' not in record and '\r' not in record.rstrip('\r'))
    result = []
    group = []
    counts = {'groups_sorted': 0, 'assignments_moved': 0,
              'duplicates_removed': 0, 'duplicate_name_groups_skipped': 0,
              'literal_assignments': 0, 'parse_warning_count': warnings}

    def flush():
        if not group:
            return
        unique_adjacent = []
        for item in group:
            if unique_adjacent and item[1] == unique_adjacent[-1][1]:
                counts['duplicates_removed'] += 1
            else:
                unique_adjacent.append(item)
        names = [item[0] for item in unique_adjacent]
        ordered = unique_adjacent
        if len(set(names)) != len(names):
            counts['duplicate_name_groups_skipped'] += 1
        else:
            ordered = sorted(unique_adjacent, key=lambda item: item[0])
            if ordered != unique_adjacent:
                counts['groups_sorted'] += 1
                counts['assignments_moved'] += sum(a != b for a, b in zip(ordered, unique_adjacent))
        result.extend(item[1] for item in ordered)
        group.clear()

    for number, line in enumerate(lines, 1):
        match = LITERAL.fullmatch(line) if number in safe_lines else None
        # A final line without its newline cannot move earlier without joining
        # statements; preserve it as a barrier instead.
        if match and line.endswith('\n'):
            counts['literal_assignments'] += 1
            group.append((match.group(1), line))
        else:
            flush()
            result.append(line)
    flush()
    return ''.join(result), counts


class SafeFailure(Exception):
    """Only fixed error categories are placed in this exception."""


def read_snapshot(path):
    target = Path(path).resolve(strict=True)
    descriptor = os.open(target, os.O_RDONLY | os.O_NONBLOCK | getattr(os, 'O_NOFOLLOW', 0))
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise SafeFailure('not_regular_file')
        with os.fdopen(os.dup(descriptor), 'rb') as stream:
            data = stream.read()
    finally:
        os.close(descriptor)
    return target, data, metadata


def same_identity(a, b):
    return (a.st_dev, a.st_ino, a.st_mode, a.st_uid, a.st_gid,
            a.st_size, a.st_mtime_ns, a.st_ctime_ns) == (
            b.st_dev, b.st_ino, b.st_mode, b.st_uid, b.st_gid,
            b.st_size, b.st_mtime_ns, b.st_ctime_ns)


def captured_command(arguments):
    """Capture local metadata output privately; never propagate subprocess text."""
    try:
        result = subprocess.run(arguments, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, check=False, timeout=30)
    except (OSError, subprocess.SubprocessError):
        raise SafeFailure('metadata_operation_failed') from None
    if result.returncode:
        raise SafeFailure('metadata_operation_failed')
    return result.stdout


def darwin_metadata(path):
    """Read ACL and extended attributes into memory without displaying any data."""
    path = str(path)
    listing = captured_command(['/bin/ls', '-lde', path])
    # The header includes path, timestamps, and content size; ACL entries follow.
    # Compare only ACL entries, and check mode/owner using stat separately.
    lines = listing.splitlines()
    if not lines:
        raise SafeFailure('metadata_operation_failed')
    acl = tuple(lines[1:])
    raw_names = captured_command(['/usr/bin/xattr', path])
    try:
        names = raw_names.decode('utf-8').splitlines()
    except UnicodeError:
        raise SafeFailure('metadata_operation_failed') from None
    attributes = {}
    for name in names:
        value = captured_command(['/usr/bin/xattr', '-px', name, path])
        # xattr formats hex over multiple lines; whitespace is not attribute data.
        attributes[name] = b''.join(value.split())
    return acl, attributes


def same_permissions(a, b):
    return (stat.S_IMODE(a.st_mode), a.st_uid, a.st_gid) == (
        stat.S_IMODE(b.st_mode), b.st_uid, b.st_gid)


def same_copied_darwin_metadata(original, copied):
    """Allow only OS regeneration of the protected provenance attribute.

    Synthetic local checks established that macOS silently ignores attempts to
    delete or overwrite com.apple.provenance. Existing-file verification showed
    that native cp can therefore produce a different provenance on its new inode.
    ACLs and every other attribute must match exactly. This exception is never
    used when checking the original file for concurrent metadata changes.
    """
    original_acl, original_attributes = original
    copied_acl, copied_attributes = copied
    def portable_attributes(attributes):
        return {name: value for name, value in attributes.items()
                if name != 'com.apple.provenance'}
    return (original_acl == copied_acl and
            portable_attributes(original_attributes) == portable_attributes(copied_attributes))


def atomic_replace(original_path, target, original, updated, metadata):
    """Compare bytes and metadata before a same-directory atomic replacement."""
    temporary = None
    preserve_darwin = sys.platform == 'darwin'
    original_extended = darwin_metadata(target) if preserve_darwin else None
    try:
        descriptor, temporary = tempfile.mkstemp(prefix='.tidy-secrets-', dir=target.parent)
        os.close(descriptor)
        if preserve_darwin:
            # macOS cp preserves ACLs, xattrs, flags, owner, and mode locally.
            # Both the original and temporary copy stay on this host.
            captured_command(['/bin/cp', '-p', str(target), temporary])
        descriptor = os.open(temporary, os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0))
        try:
            if not preserve_darwin:
                created = os.fstat(descriptor)
                if (created.st_uid, created.st_gid) != (metadata.st_uid, metadata.st_gid):
                    os.fchown(descriptor, metadata.st_uid, metadata.st_gid)
                os.fchmod(descriptor, stat.S_IMODE(metadata.st_mode))
            os.ftruncate(descriptor, 0)
            with os.fdopen(os.dup(descriptor), 'wb') as stream:
                stream.write(updated)
                stream.flush()
                os.fsync(stream.fileno())
            if not same_permissions(metadata, os.fstat(descriptor)):
                raise SafeFailure('metadata_preservation_failed')
        finally:
            os.close(descriptor)
        if preserve_darwin and not same_copied_darwin_metadata(original_extended, darwin_metadata(temporary)):
            raise SafeFailure('metadata_preservation_failed')
        current_target, current, current_metadata = read_snapshot(original_path)
        if current_target != target or current != original or not same_identity(metadata, current_metadata):
            raise SafeFailure('content_conflict')
        if preserve_darwin and darwin_metadata(target) != original_extended:
            raise SafeFailure('metadata_conflict')
        os.replace(temporary, target)
        temporary = None
        return 'applied'
    finally:
        if temporary is not None:
            os.unlink(temporary)


def tidy_file(path, apply=False):
    try:
        target, original, metadata = read_snapshot(path)
        if metadata.st_nlink != 1:
            return {'status': 'hardlinked_file_unsupported'}
        # Darwin uses native cp plus private metadata verification. Elsewhere,
        # preserve the conservative refusal of unsupported extended metadata.
        if sys.platform != 'darwin':
            if not hasattr(os, 'listxattr'):
                return {'status': 'extended_metadata_unavailable'}
            if os.listxattr(target):
                return {'status': 'extended_metadata_unsupported'}
        source = original.decode('utf-8')
        updated, counts = transform(source)
        encoded = updated.encode('utf-8')
        status = 'unchanged' if encoded == original else 'would_change'
        if apply and encoded != original:
            status = atomic_replace(path, target, original, encoded, metadata)
        return dict(status=status, **counts)
    except SafeFailure as error:
        return {'status': error.args[0]}
    except UnicodeError:
        return {'status': 'unsupported_encoding'}
    except (OSError, RuntimeError, ValueError):
        return {'status': 'file_operation_failed'}


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv == ['help']:
        argv = ['--help']
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='apply guarded atomic changes (default: dry run)')
    parser.add_argument('--json', action='store_true', help='emit fixed categories and counts as JSON')
    parser.add_argument('paths', nargs='+', help='explicit files; no execution or value output')
    args = parser.parse_args(argv)
    results = [tidy_file(path, args.apply) for path in args.paths]
    if args.json:
        print(json.dumps({'files': results}, indent=2))
    else:
        for number, result in enumerate(results, 1):
            print('File', number)
            for key, value in result.items():
                print(' ', key + ':', value)
    return int(any(result['status'] not in ('unchanged', 'would_change', 'applied') for result in results))


if __name__ == '__main__':
    raise SystemExit(main())
