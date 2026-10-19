"""Owned, loopback-only llama-server process and build5092 /completion client."""
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from urllib import error, request

from chat import compact, parse_json, validate_response

MAX_RESPONSE_BYTES = 1024 * 1024


class ServerError(ValueError):
    """A concise error with the detail log location."""


def vacant_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


class Server:
    def __init__(self, chat):
        self.chat = chat
        self.config = chat.config
        self.proc = None
        self.log = None
        self.log_path = None
        self.port = None
        self.url = None
        self.ready = False
        self.key = secrets.token_hex(24)
        # Ignore proxy environment settings even for localhost.
        self.http = request.build_opener(request.ProxyHandler({}))

    def environment(self):
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(('LLAMA_ARG_', 'LLAMA_LOG_')) and k != 'LLAMA_API_KEY'}
        directory = str(self.config['llama_server'].parent)
        env['LD_LIBRARY_PATH'] = directory + (':' + env['LD_LIBRARY_PATH']
                                             if env.get('LD_LIBRARY_PATH') else '')
        return env

    def detail(self, text):
        if self.log is not None and not self.log.closed:
            try:
                self.log.write(('\n[robi] ' + text[:8192] + '\n').encode('utf-8', 'replace'))
                self.log.flush()
            except OSError:
                # A full disk must not prevent process cleanup on an error.
                pass

    def failure(self, text):
        return ServerError('{}; log: {}'.format(text, self.log_path or 'not started'))

    def http_json(self, path, payload=None, timeout=None):
        data = None if payload is None else compact(payload).encode('utf-8')
        req = request.Request(self.url + path, data=data, headers={
            'Content-Type': 'application/json', 'Authorization': 'Bearer ' + self.key})
        with self.http.open(req, timeout=timeout or self.config['timeout_seconds']) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise ValueError('HTTP response too large')
        return parse_json(raw.decode('utf-8'))

    def __enter__(self):
        if self.proc is not None:
            raise self.failure('server instance cannot be started twice')
        try:
            exe = self.config['llama_server']
            if not exe.is_file() or not os.access(str(exe), os.X_OK):
                raise self.failure('llama-server missing or not executable: ' + str(exe))
            if not self.config['model'].is_file():
                raise self.failure('GGUF model missing: ' + str(self.config['model']))
            self.config['log_dir'].mkdir(parents=True, exist_ok=True)
            fd, name = tempfile.mkstemp(prefix='llama-server-', suffix='.log', dir=str(self.config['log_dir']))
            self.log_path = Path(name)
            self.log = os.fdopen(fd, 'ab', buffering=0)
            self.port = vacant_port()
            self.url = 'http://127.0.0.1:{}'.format(self.port)
            c = self.config
            argv = [str(exe), '-m', str(c['model']), '-ngl', str(c['gpu_layers']),
                    '-t', str(c['threads']), '-c', str(c['context_length']),
                    '-b', str(c['batch_size']), '-ub', str(c['ubatch_size']),
                    '-np', '1', '--no-context-shift', '--host', '127.0.0.1',
                    '--port', str(self.port), '--api-key', self.key]
            print('[server] starting; log: ' + str(self.log_path), file=sys.stderr, flush=True)
            self.proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=self.log,
                                         stderr=subprocess.STDOUT, env=self.environment())
            started = time.monotonic()
            deadline = started + c['startup_timeout_seconds']
            while time.monotonic() < deadline:
                if self.proc.poll() is not None:
                    raise self.failure('llama-server startup failed (exit {})'.format(self.proc.returncode))
                try:
                    remaining = max(0.01, min(1.0, deadline - time.monotonic()))
                    if self.http_json('/health', timeout=remaining) == {'status': 'ok'}:
                        # /health is public. Authenticate /props too, avoiding a
                        # different process accidentally occupying the chosen port.
                        props = self.http_json('/props', timeout=remaining)
                        if not isinstance(props, dict) or self.proc.poll() is not None:
                            raise self.failure('unexpected server readiness response')
                        self.ready = True
                        print('[server] ready in {:.3f}s; pid={}'.format(
                            time.monotonic() - started, self.proc.pid), file=sys.stderr, flush=True)
                        return self
                except error.HTTPError as exc:
                    exc.close()
                    if exc.code != 503:
                        raise self.failure('startup HTTP {}'.format(exc.code))
                except (error.URLError, socket.timeout, ConnectionError):
                    pass
                time.sleep(min(0.1, max(0, deadline - time.monotonic())))
            raise self.failure('llama-server startup timed out')
        except BaseException as exc:
            # __exit__ is NOT called when __enter__ raises (including Ctrl+C).
            self.detail('startup exception: ' + repr(exc))
            self.close()
            if isinstance(exc, (OSError, ValueError)) and not isinstance(exc, ServerError):
                raise self.failure('server startup failed: ' + str(exc)[:150])
            raise

    def close(self):
        self.ready = False
        try:
            if self.proc is not None:
                if self.proc.poll() is None:
                    self.proc.terminate()
                    try:
                        self.proc.wait(timeout=self.config['shutdown_timeout_seconds'])
                    except subprocess.TimeoutExpired:
                        self.proc.kill()
                        self.proc.wait()
                else:
                    self.proc.wait()  # reap even a server that exited on its own
        finally:
            if self.log is not None:
                self.log.close()

    def __exit__(self, exc_type, exc, traceback):
        self.close()

    def infer(self, user):
        metrics = {'json_success': False, 'inference_seconds': None, 'prompt_chars': None}
        started = None
        try:
            if not self.ready or self.proc.poll() is not None:
                raise self.failure('llama-server is not running')
            prompt, sizes = self.chat.build_prompt(user)
            metrics.update(sizes)
            payload = {'prompt': prompt, 'n_predict': self.config['max_tokens'],
                       'temperature': self.config['temperature'], 'json_schema': self.chat.schema(),
                       'cache_prompt': True, 'id_slot': 0, 'stream': False}
            started = time.monotonic()
            result = self.http_json('/completion', payload)
            if not isinstance(result, dict) or not isinstance(result.get('content'), str):
                raise ValueError('unexpected /completion response structure')
            if result.get('error') or result.get('truncated') is not False:
                raise ValueError('server error or truncated/missing context status')
            if result.get('stop') is not True or result.get('stop_type') not in ('eos', 'word'):
                raise ValueError('generation incomplete (stop_type={!r})'.format(result.get('stop_type')))
            # Native /completion returns generation only. No CLI trailer cleanup.
            try:
                response = validate_response(parse_json(result['content']), self.chat.motions, self.chat.blocked)
            except ValueError:
                self.detail('rejected completion content: ' + result['content'])
                raise
            for field in ('tokens_cached', 'tokens_evaluated', 'timings'):
                metrics[field] = result.get(field)
            self.chat.remember(user, response)
            metrics.update(json_success=True, motion_id=response['motion_id'],
                           motion_name=self.chat.motions[response['motion_id']]['name']
                           if response['motion_id'] is not None else None)
            return response
        except error.HTTPError as exc:
            try:
                self.detail('HTTP {}: {}'.format(exc.code, exc.read(8192).decode('utf-8', 'replace')))
            finally:
                exc.close()
            raise self.failure('completion HTTP {}'.format(exc.code))
        except (error.URLError, OSError, ValueError) as exc:
            self.detail(str(exc))
            raise self.failure('completion failed: ' + str(exc).replace('\n', ' ')[:180])
        finally:
            if started is not None:
                metrics['inference_seconds'] = round(time.monotonic() - started, 3)
            print('[metrics] ' + compact(metrics), file=sys.stderr, flush=True)
