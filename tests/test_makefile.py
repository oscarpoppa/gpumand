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
        self.assertEqual(built(text), {'mand', 'colorize'})
        self.assertIn('nvcc', text)

    def test_cpu_is_the_same_as_the_two_named_targets(self):
        self.assertEqual(built(plan('cpu')), built(plan('mand-cpu', 'colorize')))

    def test_everything_can_be_built_together(self):
        self.assertEqual(built(plan('all', 'cpu')), {'mand', 'mand-cpu', 'colorize'})


if __name__ == '__main__':
    unittest.main()
