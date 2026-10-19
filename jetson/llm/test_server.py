"""Real loopback HTTP + owned mock subprocess; never real model inference."""
import contextlib
import copy
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

import chat
from server import Server, ServerError

GOOD = {'speech': 'こんにちは！', 'emotion': 'happy', 'action': 'greeting', 'motion_id': '004'}
# A disposable executable implementing the pinned server's relevant response shape.
FAKE = r'''
import json, os, signal, sys, time
from http.server import BaseHTTPRequestHandler, HTTPServer
args = sys.argv[1:]
mode = os.environ.get('ROBI_TEST_MODE', 'ok')
record = os.environ['ROBI_TEST_RECORD']
with open(record + '.starts', 'a') as f: f.write(str(os.getpid()) + '\n')
if mode == 'exit':
    print('VERY LONG ENGINE LOG ' * 3000, flush=True)
    sys.exit(7)
if mode == 'ignore_term': signal.signal(signal.SIGTERM, signal.SIG_IGN)
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def send_json(self, value, status=200):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(value).encode())
    def do_GET(self):
        if self.path == '/health':
            if mode in ('loading', 'ignore_term'): self.send_json({'error': 'loading'}, 503)
            elif mode == 'bad_health': self.send_json([])
            else: self.send_json({'status': 'ok'})
        elif self.path == '/props':
            if self.headers.get('Authorization') != 'Bearer ' + args[args.index('--api-key') + 1]:
                self.send_json({'error': 'wrong server'}, 401)
            else: self.send_json({'default_generation_settings': {}})
    def do_POST(self):
        payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        with open(record + '.requests', 'a') as f: f.write(json.dumps(payload) + '\n')
        if mode == 'timeout': time.sleep(5)
        if mode == 'http_error':
            self.send_json({'error': 'huge log ' * 10000}, 500)
            return
        if mode == 'bad_json':
            self.send_response(200); self.end_headers(); self.wfile.write(b'not-json'); return
        response = json.loads(os.environ['ROBI_TEST_RESPONSE'])
        result = {'content': json.dumps(response), 'stop': True, 'stop_type': 'eos',
                  'truncated': False, 'tokens_cached': 1200, 'tokens_evaluated': 1177,
                  'timings': {'prompt_n': 8, 'predicted_n': 20}}
        if mode == 'limit': result['stop_type'] = 'limit'
        if mode == 'truncated': result['truncated'] = True
        if mode == 'envelope': result = {'content': 3}
        self.send_json(result)
HTTPServer(('127.0.0.1', int(args[args.index('--port') + 1])), Handler).serve_forever()
'''


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.record = self.base / 'record'
        fake = self.base / 'llama-server'
        fake.write_text('#!' + sys.executable + '\n' + FAKE)
        fake.chmod(0o700)
        model = self.base / 'mock.gguf'
        model.touch()
        self.config = chat.load_config(chat.BASE / 'config.json')
        self.config.update(llama_server=fake, model=model, log_dir=self.base / 'logs',
                           startup_timeout_seconds=1.5, timeout_seconds=1,
                           shutdown_timeout_seconds=0.1)
        self.bot = chat.Chat(self.config)
        self.env = mock.patch.dict(os.environ, ROBI_TEST_RECORD=str(self.record),
                                   ROBI_TEST_RESPONSE=chat.compact(GOOD), ROBI_TEST_MODE='ok')
        self.env.start()
        self.addCleanup(self.env.stop)
        self.stderr = io.StringIO()
        redirect = contextlib.redirect_stderr(self.stderr)
        redirect.__enter__()
        self.addCleanup(redirect.__exit__, None, None, None)

    def assert_closed(self, server):
        self.assertFalse(server.ready)
        self.assertIsNotNone(server.proc.poll())
        self.assertTrue(server.log.closed)

    def test_multiple_turns_start_once_cache_history_and_logs(self):
        server = Server(self.bot)
        with mock.patch('server.subprocess.Popen', wraps=subprocess.Popen) as popen:
            with server:
                pid = server.proc.pid
                for user in ('こんにちは', 'またね', 'もう一度', 'ありがとう'):
                    self.assertEqual(server.infer(user), GOOD)
                    self.assertEqual(server.proc.pid, pid)
                self.assertEqual(popen.call_count, 1)
                argv = popen.call_args[0][0]
                for flag in ('-np', '--host', '--no-context-shift', '-b', '-ub'):
                    self.assertIn(flag, argv)
                self.assertEqual(argv[argv.index('-np') + 1], '1')
                self.assertNotIn('--prompt-cache', argv)
        self.assert_closed(server)
        server.close()  # idempotent
        starts = Path(str(self.record) + '.starts').read_text().splitlines()
        self.assertEqual(len(starts), 1)
        requests = [json.loads(line) for line in Path(str(self.record) + '.requests').read_text().splitlines()]
        for payload in requests:
            self.assertIs(payload['cache_prompt'], True)
            self.assertEqual(payload['id_slot'], 0)
            self.assertIs(payload['stream'], False)
            self.assertEqual(payload['json_schema'], self.bot.schema())
            self.assertNotIn('023', payload['json_schema']['properties']['motion_id']['enum'])
        self.assertIn('こんにちは', requests[1]['prompt'])
        self.assertEqual(len(self.bot.history), 3)
        self.assertEqual(self.bot.history[-1][0], 'ありがとう')
        self.assertIn('"json_success":true', self.stderr.getvalue())
        self.assertIn('"prompt_n":8', self.stderr.getvalue())
        self.assertEqual(server.log_path.stat().st_mode & 0o777, 0o600)

    def test_startup_failure_timeout_and_cleanup(self):
        for mode in ('exit', 'loading', 'ignore_term', 'bad_health'):
            with self.subTest(mode=mode), mock.patch.dict(os.environ, ROBI_TEST_MODE=mode):
                self.config['startup_timeout_seconds'] = 0.25
                server = Server(self.bot)
                with self.assertRaises(ServerError):
                    with server:
                        self.fail('must not become ready')
                self.assert_closed(server)
        self.assertNotIn('VERY LONG ENGINE LOG', self.stderr.getvalue())

    def test_popen_failure_and_startup_ctrl_c_close_log(self):
        for exc in (OSError('spawn failed'), KeyboardInterrupt()):
            server = Server(self.bot)
            with mock.patch('server.subprocess.Popen', side_effect=exc):
                with self.assertRaises(ServerError if isinstance(exc, OSError) else type(exc)):
                    server.__enter__()
            self.assertTrue(server.log.closed)
        server = Server(self.bot)
        with mock.patch.object(server, 'http_json', side_effect=KeyboardInterrupt()):
            with self.assertRaises(KeyboardInterrupt):
                server.__enter__()
        self.assert_closed(server)

    def test_http_errors_invalid_generation_and_timeout_cleanup(self):
        before = copy.deepcopy(self.bot.history)
        for mode in ('http_error', 'bad_json', 'limit', 'truncated', 'envelope', 'timeout'):
            with self.subTest(mode=mode), mock.patch.dict(os.environ, ROBI_TEST_MODE=mode):
                self.config['timeout_seconds'] = 0.15
                server = Server(self.bot)
                with self.assertRaises(ServerError):
                    with server:
                        server.infer('test')
                self.assert_closed(server)
                self.assertEqual(self.bot.history, before)
        self.assertNotIn('huge log', self.stderr.getvalue())
        self.assertIn('"json_success":false', self.stderr.getvalue())

    def test_invalid_motion_and_required_fields(self):
        for response in (dict(GOOD, motion_id='023'), dict(GOOD, motion_id='999'),
                         dict(GOOD, motion_id=4), {'speech': '不足'}, dict(GOOD, extra=True)):
            with self.subTest(response=response), mock.patch.dict(
                    os.environ, ROBI_TEST_RESPONSE=chat.compact(response)):
                server = Server(self.bot)
                with self.assertRaises(ServerError):
                    with server:
                        server.infer('test')
                self.assert_closed(server)
                self.assertEqual(self.bot.history, [])

    def test_main_once_error_interactive_ctrl_c_and_eof(self):
        config = self.base / 'config.json'
        config.write_text(json.dumps({k: str(v) if isinstance(v, Path) else v
                                      for k, v in self.config.items()}))
        argv = [sys.executable, str(chat.BASE / 'chat.py'), '--config', str(config)]
        once = subprocess.run(argv + ['--once', 'こんにちは'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(once.returncode, 0, once.stderr)
        self.assertEqual(json.loads(once.stdout), GOOD)
        with mock.patch.dict(os.environ, ROBI_TEST_MODE='http_error'):
            failed = subprocess.run(argv + ['--once', 'こんにちは'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(failed.returncode, 1)
        self.assertEqual(failed.stdout, b'')
        self.assertLess(len(failed.stderr), 1500)
        eof = subprocess.run(argv, input=b'', stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(eof.returncode, 0)
        quit_result = subprocess.run(argv, input=b'/quit\n', stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(quit_result.returncode, 0)
        child = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            while True:
                line = child.stderr.readline()
                self.assertTrue(line, 'chat exited before readiness')
                if b'[server] ready' in line:
                    break
            child.send_signal(signal.SIGINT)
            child.communicate(timeout=5)
            self.assertEqual(child.returncode, 130)
        finally:
            if child.poll() is None:
                child.kill()
                child.communicate()
        for pid in Path(str(self.record) + '.starts').read_text().splitlines():
            with self.assertRaises(ProcessLookupError):
                os.kill(int(pid), 0)


if __name__ == '__main__':
    unittest.main()
