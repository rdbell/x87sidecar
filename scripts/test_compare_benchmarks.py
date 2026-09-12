"""The comparison runner must wait for target EOF and bound orphaned targets."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('compare', Path(__file__).with_name('compare_benchmarks.py'))
compare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(compare)


class TargetLifetime(unittest.TestCase):
    def test_waits_for_child_after_launcher_exits(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / 'target.log'
            result = compare.run([sys.executable, '-c',
                'import os,time; child=os.fork(); os._exit(0) if child else None; '
                'time.sleep(.3); print("target finished", flush=True)'], log, 5)
            self.assertEqual(result['exit'], 0)
            self.assertGreaterEqual(result['seconds'], .3)
            self.assertEqual(log.read_text().strip(), 'target finished')

    def test_bounds_child_after_launcher_exits(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / 'target.log'
            result = compare.run([sys.executable, '-c',
                'import os,time; child=os.fork(); os._exit(0) if child else None; '
                'time.sleep(30); print("should not finish", flush=True)'], log, .3)
            self.assertEqual(result['exit'], 124)
            self.assertLess(result['seconds'], 3)
            self.assertNotIn('should not finish', log.read_text())


if __name__ == '__main__':
    unittest.main()
