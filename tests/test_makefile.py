"""The makefile's targets build what they should (checked with `make -n -B`, which prints commands without running them)."""
import os
import subprocess
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))


def plan(*targets):
    out = subprocess.run(['make', '-n', '-B', *targets], cwd=ROOT, capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    return out.stdout


def built(text):
    """Names of the programs the planned commands link (-o NAME)."""
    words = text.split()
    return {words[i + 1] for i, w in enumerate(words) if w == '-o' and i + 1 < len(words) and '.' not in words[i + 1]}


class Makefile(unittest.TestCase):
    def test_cpu_target_builds_mand_cpu_and_colorize_without_cuda(self):
        text = plan('cpu')
        self.assertEqual(built(text), {'mand-cpu', 'colorize'})
        self.assertNotIn('nvcc', text)

    def test_default_target_builds_the_cuda_renderer_and_colorize_only(self):
        text = plan()
        self.assertEqual(built(text), {'mand-gpu', 'colorize'})
        self.assertIn('nvcc', text)

    def test_gpu_target_builds_mand_gpu_and_colorize_and_matches_the_default(self):
        text = plan('gpu')
        self.assertEqual(built(text), {'mand-gpu', 'colorize'})
        self.assertIn('nvcc', text)
        self.assertEqual(built(text), built(plan()))

    def test_the_gpu_program_comes_from_a_source_named_like_the_cpu_one(self):
        self.assertTrue(os.path.exists(os.path.join(ROOT, 'mand-gpu.cu')) and os.path.exists(os.path.join(ROOT, 'mand-cpu.c')))
        self.assertFalse(os.path.exists(os.path.join(ROOT, 'mand-main.cu')))

    def test_clean_removes_the_old_program_name_too(self):
        out = subprocess.run(['make', '-n', 'clean'], cwd=ROOT, capture_output=True, text=True).stdout
        self.assertTrue(all(name in out.split() for name in ('mand-gpu', 'mand-cpu', 'colorize', 'mand')), out)

    def test_cpu_is_the_same_as_the_two_named_targets(self):
        self.assertEqual(built(plan('cpu')), built(plan('mand-cpu', 'colorize')))

    def test_everything_can_be_built_together(self):
        self.assertEqual(built(plan('all', 'cpu')), {'mand-gpu', 'mand-cpu', 'colorize'})


if __name__ == '__main__':
    unittest.main()
