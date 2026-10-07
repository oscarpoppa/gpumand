"""Running the renderer so that it can never outlive the window that started it.

The GUI draws a view by running mand-cpu or mand-gpu and waiting for it. A deep view or a high iteration limit can
take hours, and the window is frozen meanwhile, so the usual way out is to close or kill it. Without care the
renderer then carries on alone, using every core until it finishes. Here the renderer is started so that:

  * the kernel sends it SIGTERM the moment its parent dies, however the parent died (even SIGKILL), and
  * if the GUI is told to stop (SIGTERM, SIGHUP, SIGINT) it stops the renderer first.
"""
import ctypes
import os
import signal
import subprocess
import sys

PR_SET_PDEATHSIG = 1
CHILD = None                        # the renderer running now, if any


def _die_with_parent():
    """Runs in the new process just before it executes the renderer (Linux; elsewhere it does nothing)."""
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        libc.prctl(PR_SET_PDEATHSIG, signal.SIGTERM, 0, 0, 0)
        if os.getppid() == 1:       # the parent was already gone before the request took effect
            os._exit(1)
    except (OSError, AttributeError):
        pass


CANCELED = None                     # what run() returns for a command that was canceled


def run(cmd, canceled=None, interval=0.05):
    """Run the command and wait for it; returns its exit status. Raises OSError if it cannot be started.
    The command is stopped if this process dies or is told to stop while it runs.

    With `canceled`, a function, it is called every `interval` seconds while waiting (the GUI keeps its window alive
    there); if it returns true the command is stopped and CANCELED (None) is returned."""
    global CHILD
    preexec = _die_with_parent if sys.platform.startswith('linux') else None
    CHILD = subprocess.Popen(cmd, preexec_fn=preexec)
    try:
        if canceled is None:
            return CHILD.wait()
        while True:
            try:
                return CHILD.wait(timeout=interval)
            except subprocess.TimeoutExpired:
                if canceled():
                    CHILD.terminate()
                    try:
                        CHILD.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        CHILD.kill()
                        CHILD.wait()
                    return CANCELED
    finally:
        CHILD = None


def stop_child():
    """Tell the running renderer, if there is one, to stop. (Signals only: this runs inside a signal handler while
    the main thread is waiting on the same Popen object, so it must not wait on it too.)"""
    child = CHILD
    if child is not None and child.returncode is None:
        try:
            os.kill(child.pid, signal.SIGTERM)
        except OSError:
            pass


def _on_signal(number, frame):
    stop_child()
    os._exit(128 + number)


def stop_with_the_renderer():
    """From now on SIGTERM, SIGHUP and SIGINT stop the renderer and then this process."""
    for number in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
        signal.signal(number, _on_signal)
