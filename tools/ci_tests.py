"""Run the unit tests the way CI does, and make failures readable without signing in to GitHub.

    python tools/ci_tests.py

Same as `python -m unittest discover -s tests -v`, plus: under GitHub Actions every failing / erroring test is also
written as an error annotation (title = test name, text = the end of its traceback). Annotations are public on a
public repository (run page and API), raw logs are not. Exit code 1 if anything failed.
"""
import faulthandler
import os
import platform
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _escape(text):
    return text.replace('%', '%25').replace('\r', '').replace('\n', '%0A')


def main():
    faulthandler.enable()
    os.chdir(ROOT)
    sys.path.insert(0, ROOT)
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    print(f'python {sys.version.split()[0]} on {platform.platform()} | QT_QPA_PLATFORM={os.environ["QT_QPA_PLATFORM"]} '
          f'| temp {tempfile.gettempdir()} | DP3D_DATA={os.environ.get("DP3D_DATA")}', flush=True)
    suite = unittest.defaultTestLoader.discover(os.path.join(ROOT, 'tests'), top_level_dir=os.path.join(ROOT, 'tests'))
    result = unittest.TextTestRunner(verbosity=2, stream=sys.stdout).run(suite)
    problems = [('FAIL', t, tb) for t, tb in result.failures] + [('ERROR', t, tb) for t, tb in result.errors]
    problems += [('ERROR', t, 'unexpected success') for t in result.unexpectedSuccesses]
    if os.environ.get('GITHUB_ACTIONS') == 'true':
        for kind, test, tb in problems[:10]:                       # GitHub shows at most 10 error annotations a step
            name = test.id().rsplit('.', 1)[-1]
            print(f'::error title={kind} {name}::{_escape(tb[-3000:])}', flush=True)
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    sys.exit(main())
