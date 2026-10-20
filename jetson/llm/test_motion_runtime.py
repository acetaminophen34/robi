"""Repository-only runtime and serial cleanup checks (Python 3.6+)."""
import contextlib
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import robi_chat_motion as runtime


class RuntimeTests(unittest.TestCase):
    def test_repository_assets_and_missing_index(self):
        self.assertEqual(runtime.ROOT, Path(runtime.__file__).resolve().parents[2])
        with patch.object(runtime, 'MOTIONS', runtime.MOTIONS):
            entries = runtime.prepare(runtime.ROOT / 'motion_editor/motions/index.json')
            self.assertIn('001', entries)
            self.assertIn('002', entries)
            with tempfile.TemporaryDirectory() as folder:
                missing = Path(folder) / 'index.json'
                with self.assertRaisesRegex(FileNotFoundError, 'Required local file missing'):
                    runtime.prepare(missing)
                self.assertFalse(missing.exists())

    def test_dry_run_never_opens_serial(self):
        with patch.object(runtime, 'MOTIONS', runtime.MOTIONS):
            entries = runtime.prepare(runtime.ROOT / 'motion_editor/motions/index.json')
            with patch.object(runtime.serial, 'Serial', side_effect=AssertionError('serial opened')):
                with contextlib.redirect_stdout(io.StringIO()) as output:
                    robot = runtime.DryRunRobi()
                    for mid in ('001', '003', '002'):
                        robot.play(runtime.load_motion(entries, mid), mid)
                    robot.close()
                self.assertEqual(robot.state, 'crouched')
                self.assertIn('[dry-run] STOP', output.getvalue())

    def test_ping_failure_closes_serial(self):
        with patch.object(runtime.serial, 'Serial') as serial_cls:
            with patch.object(runtime.time, 'sleep'):
                with patch.object(runtime.SerialRobi, 'send', side_effect=TimeoutError('no PING')):
                    with self.assertRaises(TimeoutError):
                        runtime.SerialRobi('/dev/mock')
            serial_cls.return_value.close.assert_called_once_with()

    def test_config_environment_paths(self):
        from chat import load_config
        with tempfile.TemporaryDirectory() as folder:
            model = str(Path(folder) / 'model.gguf')
            server = str(Path(folder) / 'llama-server')
            index = str(Path(folder) / 'motions/index.json')
            with patch.dict(os.environ, {'ROBI_MODEL': model, 'ROBI_LLAMA_SERVER': server,
                                        'ROBI_MOTION_INDEX': index}):
                config = load_config(runtime.LLM / 'config.json')
            self.assertEqual(config['model'], Path(model).resolve())
            self.assertEqual(config['llama_server'], Path(server).resolve())
            self.assertEqual(config['motion_index'], Path(index).resolve())


if __name__ == '__main__':
    unittest.main()
