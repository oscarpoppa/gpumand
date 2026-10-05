"""Unit tests for cleanup.py: what counts as a generated file, and what is never touched."""
import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import cleanup

GENERATED = ['mandapp0.bmp', 'mandapp4.bmp.new', 'whole-start.bmp.new', 'mandapp12.bmp', 'mandapp12.bmp.nu', 'mandapp3.c7.bmp', 'mandapp3.c120.bmp',
             'whole-start.bmp', 'whole.bmp.nu', 'whole.c1.bmp', 'whole.c33.bmp']
KEPT = ['mandapp3.png', 'whole-start.png', 'mandapp1.bmp.png', 'view.png', 'view.png.part', 'whole.bmp', 'mine.bmp', 'mandapp.bmp', 'mandappX.bmp', 'mandapp1.bmp.bak', 'mandapp1.bmp.nu.old', 'mandapp1.cX.bmp',
        'xmandapp1.bmp', 'mandapp1.bmp~', 'notes.txt', 'mand-gui.ini', 'whole.bmp.nu.keep', 'whole-start.bmp.1']


class Cleanup(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        self.addCleanup(self.tmp.cleanup)

    def make(self, name, data=b'x' * 10, age=0):
        path = os.path.join(self.dir, name)
        with open(path, 'wb') as fp:
            fp.write(data)
        if age:
            os.utime(path, (time.time() - age, time.time() - age))
        return path

    def names(self, paths):
        return sorted(os.path.basename(p) for p in paths)

    def test_matches_exactly_the_names_the_program_makes(self):
        for n in GENERATED + KEPT:
            self.make(n)
        self.assertEqual(self.names(cleanup.generated_files(self.dir)), sorted(GENERATED))

    def test_the_opening_views_files_can_be_left_out(self):
        for n in GENERATED + KEPT:
            self.make(n)
        self.make('mandapp5.bmp.ref')
        got = self.names(cleanup.generated_files(self.dir, opening=False))
        self.assertEqual(got, sorted(n for n in GENERATED if not n.startswith('whole')) + ['mandapp5.bmp.ref'])
        self.assertEqual(len(cleanup.generated_files(self.dir)), len(GENERATED) + 1)

    def test_reference_files_are_generated_too(self):
        refs = ['mandapp5.bmp.ref', 'mandapp5.bmp.new.ref', 'whole-start.bmp.new.ref']
        for n in refs + ['other.ref', 'whole.bmp.ref']:
            self.make(n)
        self.assertEqual(self.names(cleanup.generated_files(self.dir)), sorted(refs))

    def test_directories_and_links_are_not_matched(self):
        os.mkdir(os.path.join(self.dir, 'mandapp1.bmp'))
        target = self.make('precious.bmp')
        os.symlink(target, os.path.join(self.dir, 'mandapp2.bmp'))
        self.assertEqual(cleanup.generated_files(self.dir), [])
        self.assertEqual(cleanup.delete_files(cleanup.generated_files(self.dir)), 0)
        self.assertTrue(os.path.exists(target))

    def test_delete_removes_only_what_it_was_given(self):
        for n in GENERATED + KEPT:
            self.make(n)
        self.assertEqual(cleanup.delete_files(cleanup.generated_files(self.dir)), 0)
        self.assertEqual(sorted(os.listdir(self.dir)), sorted(KEPT))

    def test_missing_directory_and_files_are_harmless(self):
        gone = os.path.join(self.dir, 'nope')
        self.assertEqual(cleanup.generated_files(gone), [])
        self.assertEqual(cleanup.delete_files([os.path.join(self.dir, 'mandapp1.bmp')]), 0)

    def test_failed_deletes_are_counted(self):
        path = self.make('mandapp1.bmp')
        os.chmod(self.dir, 0o500)
        try:
            if os.access(self.dir, os.W_OK):
                self.skipTest('running as a user who can write anyway')
            self.assertEqual(cleanup.delete_files([path]), 1)
        finally:
            os.chmod(self.dir, 0o700)

    def test_total_size(self):
        paths = [self.make('mandapp1.bmp', b'a' * 100), self.make('mandapp1.bmp.nu', b'b' * 250)]
        self.assertEqual(cleanup.total_size(paths), 350)
        self.assertEqual(cleanup.total_size(paths + [os.path.join(self.dir, 'gone')]), 350)

    def test_only_old_reference_files_are_swept(self):
        old = self.make('mandapp1.bmp.ref', age=7200)
        fresh = self.make('mandapp2.bmp.ref', age=5)
        image = self.make('mandapp1.bmp', age=7200)
        removed = cleanup.remove_stale_references(self.dir)
        self.assertEqual(removed, [old])
        self.assertFalse(os.path.exists(old))
        self.assertTrue(os.path.exists(fresh) and os.path.exists(image))

    def test_move_files_into_a_new_dated_folder(self):
        paths = [self.make('mandapp1.bmp', b'a' * 5), self.make('mandapp1.bmp.nu', b'b' * 7)]
        other = self.make('whole.bmp', b'keep')
        dest = os.path.join(self.dir, 'out')
        os.mkdir(dest)
        folder, failed = cleanup.move_files(paths, dest, now=1700000000)
        self.assertEqual(failed, 0)
        self.assertEqual(os.path.dirname(folder), dest)
        self.assertTrue(os.path.basename(folder).startswith('mandelbrot-2023'))
        self.assertEqual(sorted(os.listdir(folder)), ['mandapp1.bmp', 'mandapp1.bmp.nu'])
        self.assertEqual(open(os.path.join(folder, 'mandapp1.bmp.nu'), 'rb').read(), b'b' * 7)
        self.assertFalse(any(os.path.exists(p) for p in paths))
        self.assertTrue(os.path.exists(other))

    def test_moving_twice_never_overwrites(self):
        dest = os.path.join(self.dir, 'out')
        os.mkdir(dest)
        a = self.make('mandapp1.bmp', b'first')
        f1, _ = cleanup.move_files([a], dest, now=1700000000)
        b = self.make('mandapp1.bmp', b'second')
        f2, _ = cleanup.move_files([b], dest, now=1700000000)      # same second
        self.assertNotEqual(f1, f2)
        self.assertEqual(open(os.path.join(f1, 'mandapp1.bmp'), 'rb').read(), b'first')
        self.assertEqual(open(os.path.join(f2, 'mandapp1.bmp'), 'rb').read(), b'second')

    def test_files_that_cannot_be_moved_are_counted(self):
        dest = os.path.join(self.dir, 'out')
        os.mkdir(dest)
        folder, failed = cleanup.move_files([os.path.join(self.dir, 'mandapp9.bmp')], dest)
        self.assertEqual(failed, 1)

    def test_only_pictures_are_worth_keeping(self):
        paths = [os.path.join(self.dir, n) for n in ('mandapp1.bmp', 'mandapp1.bmp.nu', 'mandapp2.c3.bmp', 'whole-start.bmp',
                                                    'mandapp1.bmp.ref', 'mandapp1.bmp.new', 'whole.bmp.nu')]
        images, rest = cleanup.split_images(paths)
        self.assertEqual([os.path.basename(p) for p in images], ['mandapp1.bmp', 'mandapp2.c3.bmp', 'whole-start.bmp'])
        self.assertEqual([os.path.basename(p) for p in rest], ['mandapp1.bmp.nu', 'mandapp1.bmp.ref', 'mandapp1.bmp.new', 'whole.bmp.nu'])

    def test_view_files_are_that_view_only(self):
        mine = ['mandapp1.bmp', 'mandapp1.bmp.nu', 'mandapp1.bmp.new', 'mandapp1.bmp.nu.new', 'mandapp1.bmp.ref',
                'mandapp1.bmp.new.ref', 'mandapp1.c3.bmp', 'mandapp1.c12.bmp']
        others = ['mandapp10.bmp', 'mandapp10.bmp.nu', 'mandapp11.c1.bmp', 'mandapp2.bmp', 'mandapp2.bmp.nu', 'whole-start.bmp',
                  'whole.bmp', 'whole.bmp.nu', 'mandapp1.png', 'mandapp1x.bmp', 'mandapp1.bmp.bak', 'mandapp1.cx.bmp', 'xmandapp1.bmp']
        for n in mine + others:
            self.make(n)
        got = cleanup.view_files(self.dir, os.path.join(self.dir, 'mandapp1.bmp'))
        self.assertEqual(self.names(got), sorted(mine))
        self.assertEqual(self.names(cleanup.view_files(self.dir, 'mandapp10.bmp')), ['mandapp10.bmp', 'mandapp10.bmp.nu'])

    def test_view_files_refuses_other_names(self):
        self.make('whole.bmp')
        self.make('whole-start.bmp')
        for name in ('whole.bmp', 'whole-start.bmp', 'mandapp.bmp', 'mandappX.bmp', 'mandapp1.png', '../mandapp1.bmp.nu', ''):
            self.assertEqual(cleanup.view_files(self.dir, name), [], name)

    def test_size_text(self):
        self.assertEqual(cleanup.size_text(500), '500 bytes')
        self.assertEqual(cleanup.size_text(2048), '2.0 KB')
        self.assertEqual(cleanup.size_text(5 * (1 << 20)), '5.0 MB')
        self.assertEqual(cleanup.size_text(3 * (1 << 30) // 2), '1.5 GB')


if __name__ == '__main__':
    unittest.main()
