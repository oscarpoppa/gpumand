#!/usr/bin/env python3
"""Runs tests/gui_driver.py, which drives the real mand-gui.py under an offscreen Qt platform
with a fake `mand` binary. Skipped when PyQt5 is not installed."""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))


def have_pyqt():
    return subprocess.run([sys.executable, '-c', 'import PyQt5.QtWidgets'], capture_output=True).returncode == 0


@unittest.skipUnless(have_pyqt(), 'PyQt5 not installed')
class GuiSmoke(unittest.TestCase):
    def test_gui_flows(self):
        with tempfile.TemporaryDirectory() as tmp:
            res = subprocess.run([sys.executable, os.path.join(HERE, 'gui_driver.py'), tmp],
                                 env=dict(os.environ, QT_QPA_PLATFORM='offscreen'),
                                 capture_output=True, text=True, timeout=300)
        report = '\n'.join(l for l in res.stdout.split('\n') if l.startswith(('ok', 'FAIL')))
        self.assertEqual(res.returncode, 0, report + '\n' + res.stderr[-2000:])
        self.assertGreaterEqual(report.count('\nok') + 1, 15, report)


@unittest.skipUnless(have_pyqt() and shutil.which('gcc') and shutil.which('make'), 'needs PyQt5, gcc and make')
class GuiWithRealRenderer(unittest.TestCase):
    """The GUI end to end against the real mand-cpu renderer: no fakes anywhere."""

    def test_gui_with_mand_cpu(self):
        built = subprocess.run(['make', '-C', os.path.join(HERE, '..'), 'mand-cpu', 'colorize'], capture_output=True, text=True)
        if built.returncode:
            self.skipTest('mand-cpu does not build here (OpenMP?): ' + built.stderr[-300:])
        with tempfile.TemporaryDirectory() as tmp:
            res = subprocess.run([sys.executable, os.path.join(HERE, 'gui_driver.py'), tmp, '--real'],
                                 env=dict(os.environ, QT_QPA_PLATFORM='offscreen'),
                                 capture_output=True, text=True, timeout=600)
        report = '\n'.join(l for l in res.stdout.split('\n') if l.startswith(('ok', 'FAIL')))
        self.assertEqual(res.returncode, 0, report + '\n' + res.stderr[-2000:])


if __name__ == '__main__':
    unittest.main()
