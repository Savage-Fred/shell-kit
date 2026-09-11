#!/usr/bin/env python3
"""Synthetic values only; never inspect real credentials."""
import contextlib
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import tidy_secrets as tidy

CANARY = 'C4NARY_do_not_disclose'


class TidyTests(unittest.TestCase):
    def test_literal_sort_preserves_assignment_bytes(self):
        source = '  export Z="space = ' + CANARY + '"  \nA=\'literal $not_expanded\'\nM=abc=123\n'
        expected = "A='literal $not_expanded'\nM=abc=123\n" + source.splitlines(keepends=True)[0]
        result, counts = tidy.transform(source)
        self.assertEqual(result, expected)
        self.assertEqual(counts['groups_sorted'], 1)
        self.assertNotIn(CANARY, json.dumps(counts))

    def test_barriers(self):
        for barrier in ('# comment\n', '\n', 'REF="$Z"\n', 'RUN=$(echo x)\n',
                        'A=x B=y\n', 'A = bad\n', 'A=x # comment\n',
                        'export A="has\\nescape"\n', 'A=~\n', 'readonly A=x\n'):
            source = 'Z=z\n' + barrier + 'A=a\n'
            self.assertEqual(tidy.transform(source)[0], source)

    def test_identical_adjacent_duplicate(self):
        source = 'Z=' + CANARY + '\nZ=' + CANARY + '\nA=a\n'
        result, counts = tidy.transform(source)
        self.assertEqual(result, 'A=a\nZ=' + CANARY + '\n')
        self.assertEqual(counts['duplicates_removed'], 1)

    def test_duplicates_never_cross_barrier(self):
        source = 'A=a\n# comment\nA=a\n'
        self.assertEqual(tidy.transform(source)[0], source)

    def test_different_duplicate_values_preserve_order(self):
        source = 'Z=z\nA=first\nA=second\nB=b\n'
        result, counts = tidy.transform(source)
        self.assertEqual(result, source)
        self.assertEqual(counts['duplicate_name_groups_skipped'], 1)

    def test_nonadjacent_identical_duplicates_stay(self):
        source = 'Z=z\nA=a\nZ=z\n'
        self.assertEqual(tidy.transform(source)[0], source)

    def test_multiline_fake_assignments_untouched(self):
        for wrapper in (("PAYLOAD='", "'\n"), ('PAYLOAD="', '"\n'), ('PAYLOAD=$(', ')\n'),
                        ('PAYLOAD=(', ')\n'), ('PAYLOAD=`', '`\n')):
            source = wrapper[0] + '\nZ=' + CANARY + '\nA=a\n' + wrapper[1]
            self.assertEqual(tidy.transform(source)[0], source)

    def test_unclosed_and_heredoc(self):
        for source in ("PAYLOAD='\nZ=z\nA=a\n", 'cat <<EOF\nZ=z\nA=a\nEOF\n'):
            self.assertEqual(tidy.transform(source)[0], source)

    def test_empty_and_unsupported(self):
        for source in ('', '# comments\n', 'echo hello\n', 'Z=z; A=a\n'):
            self.assertEqual(tidy.transform(source)[0], source)

    def test_final_no_newline_is_barrier(self):
        source = 'Z=z\nA=a'
        self.assertEqual(tidy.transform(source)[0], source)

    def test_crlf_preserved(self):
        source = 'Z=z\r\nA=a\r\n'
        self.assertEqual(tidy.transform(source)[0], 'A=a\r\nZ=z\r\n')

    def test_non_newline_separators_never_split_payload(self):
        source = "PAYLOAD='x\vZ=z\vA=a'\n"
        self.assertEqual(tidy.transform(source)[0], source)

    def test_dry_run_and_apply_mode(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'synthetic'
            path.write_bytes(b'Z=z\nA=a\n')
            path.chmod(0o640)
            old_inode = path.stat().st_ino
            self.assertEqual(tidy.tidy_file(path)['status'], 'would_change')
            self.assertEqual(path.read_bytes(), b'Z=z\nA=a\n')
            self.assertEqual(tidy.tidy_file(path, apply=True)['status'], 'applied')
            self.assertEqual(path.read_bytes(), b'A=a\nZ=z\n')
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o640)
            self.assertNotEqual(path.stat().st_ino, old_inode)
            self.assertEqual(list(Path(folder).glob('.tidy-secrets-*')), [])
            self.assertEqual(tidy.tidy_file(path, apply=True)['status'], 'unchanged')

    def test_symlink_preserves_link_edits_target(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'target'
            target.write_text('Z=z\nA=a\n')
            link = Path(folder) / 'link'
            link.symlink_to('target')
            self.assertEqual(tidy.tidy_file(link, apply=True)['status'], 'applied')
            self.assertTrue(link.is_symlink())
            self.assertEqual(target.read_text(), 'A=a\nZ=z\n')

    def test_content_conflict_preserves_concurrent_edit(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'synthetic'
            path.write_text('Z=z\nA=a\n')
            real_read = tidy.read_snapshot
            calls = 0
            def changed_read(argument):
                nonlocal calls
                calls += 1
                if calls == 2:
                    path.write_text('CONCURRENT=preserve\n')
                return real_read(argument)
            with mock.patch.object(tidy, 'read_snapshot', side_effect=changed_read):
                self.assertEqual(tidy.tidy_file(path, apply=True)['status'], 'content_conflict')
            self.assertEqual(path.read_text(), 'CONCURRENT=preserve\n')
            self.assertEqual(list(Path(folder).glob('.tidy-secrets-*')), [])

    def test_symlink_retarget_conflict(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'target'
            target.write_text('Z=z\nA=a\n')
            other = Path(folder) / 'other'
            other.write_text('PRIVATE=preserve\n')
            link = Path(folder) / 'link'
            link.symlink_to('target')
            real_read = tidy.read_snapshot
            calls = 0
            def changed_read(argument):
                nonlocal calls
                calls += 1
                if calls == 2:
                    link.unlink()
                    link.symlink_to('other')
                return real_read(argument)
            with mock.patch.object(tidy, 'read_snapshot', side_effect=changed_read):
                self.assertEqual(tidy.tidy_file(link, apply=True)['status'], 'content_conflict')
            self.assertEqual(target.read_text(), 'Z=z\nA=a\n')
            self.assertEqual(other.read_text(), 'PRIVATE=preserve\n')

    def test_atomic_replace_failure_keeps_original_cleans_temp(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'synthetic'
            path.write_text('Z=z\nA=a\n')
            with mock.patch.object(tidy.os, 'replace', side_effect=OSError(CANARY)):
                result = tidy.tidy_file(path, apply=True)
            self.assertEqual(result['status'], 'file_operation_failed')
            self.assertNotIn(CANARY, json.dumps(result))
            self.assertEqual(path.read_text(), 'Z=z\nA=a\n')
            self.assertEqual(list(Path(folder).glob('.tidy-secrets-*')), [])

    def test_no_values_names_paths_in_output(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / CANARY
            path.write_text('Z=' + CANARY + '\nA=a\n')
            for args in ([str(path)], ['--json', str(path)], ['--apply', str(path)]):
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    self.assertEqual(tidy.main(args), 0)
                self.assertNotIn(CANARY, output.getvalue())
                self.assertNotIn('Z=', output.getvalue())

    def test_hardlink_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'synthetic'
            path.write_text('Z=z\nA=a\n')
            os.link(path, Path(folder) / 'hardlink')
            self.assertEqual(tidy.tidy_file(path, apply=True)['status'], 'hardlinked_file_unsupported')

    def test_darwin_metadata_capture_excludes_header(self):
        outputs = [b'-rw-------+ user group 123 date private-path\n 0: user:somebody allow read\n',
                   b'com.example.synthetic\n', b'43 34 4e 41 52 59\n']
        with mock.patch.object(tidy, 'captured_command', side_effect=outputs):
            acl, attributes = tidy.darwin_metadata('/synthetic/path')
        self.assertEqual(acl, (b' 0: user:somebody allow read',))
        self.assertEqual(attributes, {'com.example.synthetic': b'43344e415259'})

    def test_subprocess_error_is_fixed_category(self):
        result = subprocess.CompletedProcess([], 1, CANARY.encode(), CANARY.encode())
        with mock.patch.object(tidy.subprocess, 'run', return_value=result):
            with self.assertRaises(tidy.SafeFailure) as caught:
                tidy.captured_command(['/synthetic/tool'])
        self.assertEqual(str(caught.exception), 'metadata_operation_failed')

    def darwin_case(self, metadata_sequence, preserve_mode=True):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        path = Path(folder.name) / 'synthetic'
        path.write_text('Z=z\nA=a\n')
        path.chmod(0o640)
        def fake_copy(args):
            self.assertEqual(args[:2], ['/bin/cp', '-p'])
            destination = Path(args[3])
            destination.write_bytes(Path(args[2]).read_bytes())
            if preserve_mode:
                destination.chmod(0o640)
            return b''
        with mock.patch.object(tidy.sys, 'platform', 'darwin'), \
                mock.patch.object(tidy, 'captured_command', side_effect=fake_copy), \
                mock.patch.object(tidy, 'darwin_metadata', side_effect=metadata_sequence):
            result = tidy.tidy_file(path, apply=True)
        self.assertNotIn(CANARY, json.dumps(result))
        self.assertEqual(list(Path(folder.name).glob('.tidy-secrets-*')), [])
        return path, result

    def test_darwin_metadata_preserved(self):
        metadata = ((b'private-acl',), {'private-attr': CANARY.encode()})
        path, result = self.darwin_case([metadata, metadata, metadata])
        self.assertEqual(result['status'], 'applied')
        self.assertEqual(path.read_text(), 'A=a\nZ=z\n')
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o640)

    def test_darwin_provenance_only_regeneration_allowed(self):
        original = ((b'private-acl',), {'com.apple.provenance': b'old', 'user-attr': CANARY.encode()})
        copied = ((b'private-acl',), {'com.apple.provenance': b'new', 'user-attr': CANARY.encode()})
        path, result = self.darwin_case([original, copied, original])
        self.assertEqual(result['status'], 'applied')
        self.assertEqual(path.read_text(), 'A=a\nZ=z\n')

    def test_darwin_added_provenance_allowed(self):
        original = ((), {})
        copied = ((), {'com.apple.provenance': b'regenerated'})
        path, result = self.darwin_case([original, copied, original])
        self.assertEqual(result['status'], 'applied')
        self.assertEqual(path.read_text(), 'A=a\nZ=z\n')

    def test_darwin_user_xattr_difference_still_refused(self):
        original = ((), {'com.apple.provenance': b'old', 'user-attr': CANARY.encode()})
        copied = ((), {'com.apple.provenance': b'new', 'user-attr': b'changed'})
        path, result = self.darwin_case([original, copied])
        self.assertEqual(result['status'], 'metadata_preservation_failed')
        self.assertEqual(path.read_text(), 'Z=z\nA=a\n')

    def test_darwin_source_provenance_conflict_remains_strict(self):
        original = ((), {'com.apple.provenance': b'old'})
        copied = ((), {'com.apple.provenance': b'new'})
        path, result = self.darwin_case([original, copied, copied])
        self.assertEqual(result['status'], 'metadata_conflict')
        self.assertEqual(path.read_text(), 'Z=z\nA=a\n')

    def test_darwin_acl_difference_still_refused(self):
        original = ((b'original-acl',), {'com.apple.provenance': b'old'})
        copied = ((b'changed-acl',), {'com.apple.provenance': b'new'})
        path, result = self.darwin_case([original, copied])
        self.assertEqual(result['status'], 'metadata_preservation_failed')
        self.assertEqual(path.read_text(), 'Z=z\nA=a\n')

    def test_darwin_copy_metadata_loss_refused(self):
        path, result = self.darwin_case([((), {'attr': CANARY.encode()}), ((), {})])
        self.assertEqual(result['status'], 'metadata_preservation_failed')
        self.assertEqual(path.read_text(), 'Z=z\nA=a\n')

    def test_darwin_mode_loss_refused(self):
        path, result = self.darwin_case([((), {})], preserve_mode=False)
        self.assertEqual(result['status'], 'metadata_preservation_failed')
        self.assertEqual(path.read_text(), 'Z=z\nA=a\n')

    def test_darwin_concurrent_metadata_change_refused(self):
        initial = ((), {'attr': CANARY.encode()})
        path, result = self.darwin_case([initial, initial, ((), {})])
        self.assertEqual(result['status'], 'metadata_conflict')
        self.assertEqual(path.read_text(), 'Z=z\nA=a\n')

    def test_other_platform_still_rejects_xattrs(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'synthetic'
            path.write_text('Z=z\nA=a\n')
            with mock.patch.object(tidy.sys, 'platform', 'linux'), \
                    mock.patch.object(tidy.os, 'listxattr', return_value=['private-attr'], create=True):
                result = tidy.tidy_file(path, apply=True)
            self.assertEqual(result['status'], 'extended_metadata_unsupported')
            self.assertEqual(path.read_text(), 'Z=z\nA=a\n')

    def test_help_aliases(self):
        script = Path(__file__).with_name('tidy_secrets.py')
        for arg in ('-h', '--help', 'help'):
            result = subprocess.run([sys.executable, str(script), arg], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0)
            self.assertIn('Dry run is the default', result.stdout)


if __name__ == '__main__':
    unittest.main()
