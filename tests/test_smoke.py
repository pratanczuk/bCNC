"""Smoke-test the real entry point without hardware, a desktop, or a pendant."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class PackageSmokeTest(unittest.TestCase):
    def test_cli_connection_preferences_and_geometry_reach_application(self):
        from copy import deepcopy
        from unittest.mock import patch
        from bCNC.__main__ import main
        import Utils
        original = deepcopy(Utils.config)
        try:
            with patch.object(sys, 'argv', ['bCNC', '--serial', 'socket://plotter.local:8888',
                                          '--baud', '57600', '-S', '-g', '800x600']), \
                    patch('bmain.Application') as application, \
                    patch('Updates.need2Check', return_value=False), \
                    patch('Utils.saveConfiguration'):
                main()
                application.return_value.geometry.assert_called_once_with('800x600')
                self.assertEqual(Utils.getStr('Connection', 'port'), 'socket://plotter.local:8888')
                self.assertEqual(Utils.getInt('Connection', 'baud'), 57600)
                self.assertFalse(Utils.getBool('Connection', 'openserial'))
        finally:
            Utils.config = original

    def test_current_entry_point_completes_package_smoke_check(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                [sys.executable, '-m', 'bCNC', '--ini', str(Path(directory) / 'settings.ini'),
                 '--package-smoke-test'],
                cwd=root, capture_output=True, text=True, timeout=30,
            )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
