#!/usr/bin/env python3
"""children.py: a renderer started by the GUI must not outlive it. Each test starts a small parent process that runs a
long `sleep` the way the GUI runs the renderer, then stops the parent in some way and checks the sleep is gone."""
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

PARENT = '''
import os, sys
sys.path.insert(0, %r)
import children
if %r:
    children.stop_with_the_renderer()
sys.exit(children.run(['sleep', '600']) %% 256)
'''


def alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    try:
        with open('/proc/%d/stat' % pid) as fp:
            return fp.read().rsplit(')', 1)[1].split()[0] != 'Z'     # (a zombie has already stopped)
    except OSError:
        return False


def wait_until(test, seconds=10):
    end = time.time() + seconds
    while time.time() < end:
        if test():
            return True
        time.sleep(0.05)
    return test()


@unittest.skipUnless(sys.platform.startswith('linux') and os.path.isdir('/proc'), 'needs Linux')
class RendererDiesWithTheGui(unittest.TestCase):
    def start(self, handlers):
        parent = subprocess.Popen([sys.executable, '-c', PARENT % (ROOT, handlers)])
        self.addCleanup(lambda: parent.poll() is None and parent.kill())
        # the sleep is the parent's only child
        found = []

        def child():
            res = subprocess.run(['pgrep', '-P', str(parent.pid)], capture_output=True, text=True)
            found[:] = [int(p) for p in res.stdout.split()]
            return bool(found)
        self.assertTrue(wait_until(child), 'the parent never started its child')
        kid = found[0]
        self.addCleanup(lambda: alive(kid) and os.kill(kid, signal.SIGKILL))
        return parent, kid

    def test_killing_the_parent_stops_the_child(self):
        parent, kid = self.start(False)
        parent.kill()
        parent.wait()
        self.assertTrue(wait_until(lambda: not alive(kid)), 'the renderer kept running after its parent was killed')

    def test_terminating_the_parent_stops_the_child(self):
        for number in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
            parent, kid = self.start(True)
            parent.send_signal(number)
            parent.wait(timeout=10)
            self.assertEqual(parent.returncode, 128 + number)
            self.assertTrue(wait_until(lambda: not alive(kid)), 'the renderer kept running after signal %d' % number)

    def test_a_finished_child_gives_its_status_and_leaves_nothing_behind(self):
        code = ('import sys; sys.path.insert(0, %r); import children; '
                'print(children.run([sys.executable, "-c", "raise SystemExit(3)"]), children.CHILD)' % ROOT)
        res = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True)
        self.assertEqual(res.stdout.strip(), '3 None', res.stderr)

    def test_a_missing_program_raises_oserror(self):
        code = ('import sys; sys.path.insert(0, %r); import children\n'
                'try:\n    children.run(["/no/such/renderer"])\nexcept OSError:\n    print("oserror", children.CHILD)' % ROOT)
        res = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True)
        self.assertEqual(res.stdout.strip(), 'oserror None', res.stderr)


if __name__ == '__main__':
    unittest.main()
