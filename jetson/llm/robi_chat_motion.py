#!/usr/bin/env python3
"""Jetson TX2: start crouched, stand, chat+motion, /quit to crouch.
Requires Python 3.6+, pyserial, an existing llama-server binary and model.
Uses repository sources and motions; never downloads runtime assets.
"""
import argparse
import json
import math
import os
from pathlib import Path
import sys
import time

import serial

ROOT = Path(__file__).resolve().parents[2]
LLM = ROOT / 'jetson' / 'llm'
MOTIONS = ROOT / 'motion_editor' / 'motions'
STANDING = 'e0075cc3fa954af19e30784876243bc3'
CORE_FILES = [
    'jetson/llm/chat.py', 'jetson/llm/server.py',
    'jetson/llm/config.json', 'jetson/llm/personality.md',
    'jetson/llm/examples.json',
]


def require_file(path):
    if not path.is_file():
        raise FileNotFoundError('Required local file missing: ' + str(path))
    return path


def prepare(index_path):
    global MOTIONS
    MOTIONS = index_path.parent
    for path in CORE_FILES:
        require_file(ROOT / path)
    index = json.loads(require_file(index_path).read_text(encoding='utf-8'))
    if index.get('format') != 'robi-motion-index-v1':
        raise ValueError('invalid motion index')
    entries = {}
    for motion in index['motions']:
        mid = motion['id']
        filename = motion['file']
        if Path(filename).name != filename or not filename.endswith('.json'):
            raise ValueError('unsafe filename in index')
        if mid in entries:
            raise ValueError('duplicate motion ID: ' + mid)
        entries[mid] = motion
        require_file(MOTIONS / filename)
    for mid in ('001', '002'):
        if mid not in entries:
            raise ValueError('required motion missing: ' + mid)
    return entries


class SerialRobi:
    def __init__(self, port):
        self.ser = serial.Serial(port, 115200, timeout=0.2, write_timeout=2)
        try:
            time.sleep(2)
            self.ser.reset_input_buffer()
            self.send('PING', 'ROBI_MOTION_V3', 4)
        except BaseException:
            self.ser.close()
            raise
        self.state = 'crouched'  # Assumption checked by the operator before start

    def send(self, command, expected, timeout=5):
        self.ser.write((command + '\n').encode('ascii'))
        self.ser.flush()
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            line = self.ser.readline().decode('utf-8', 'replace').strip()
            if not line:
                continue
            if line.startswith('ERR,'):
                raise RuntimeError('ESP32: ' + line)
            if line == expected:
                return
        raise TimeoutError('ESP32 did not respond with ' + expected)

    def frame(self, entry):
        angles = entry['angles']
        if set(angles) != {str(i) for i in range(2, 22)}:
            raise ValueError('frame must contain servo IDs 2..21')
        ms = int(round(entry['duration_ms']))
        if not 50 <= ms <= 163830:
            raise ValueError('invalid frame duration')
        values = [float(angles[str(i)]) for i in range(2, 22)]
        if any(not math.isfinite(a) or a < -3276.8 or a > 3276.7 for a in values):
            raise ValueError('invalid servo position')
        cmd = 'FRAME_RAW,{},{}'.format(ms, ','.join('{:.1f}'.format(a) for a in values))
        self.send(cmd, 'OK,FRAME', 5)
        self.state = 'unknown'  # Partial movements must not be mistaken for a known pose
        self.read_done(ms / 1000.0 + 6)

    def read_done(self, timeout):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            line = self.ser.readline().decode('utf-8', 'replace').strip()
            if line.startswith('ERR,'):
                raise RuntimeError('ESP32: ' + line)
            if line == 'DONE,FRAME':
                return
        raise TimeoutError('ESP32 motion completion timeout')

    def play(self, motion, mid):
        if motion.get('format') != 'robi-motion-v1':
            raise ValueError('unsupported motion format')
        print('[motion] {} {}'.format(mid, motion.get('name', '')), flush=True)
        torque = self.state != 'crouched'
        for frame in motion['frames']:
            kind = frame.get('type', 'pose')
            if kind == 'torque':
                torque = frame['enabled']
                self.send('TORQUE,1' if torque else 'STOP',
                          'OK,TORQUE' if torque else 'OK,STOP')
            elif kind == 'pose':
                # The 001 startup motion intentionally sends its first crouch pose
                # with torque off, matching the original JSON.
                if not torque and mid != '001':
                    raise RuntimeError('pose after torque OFF')
                self.frame(frame)
            elif kind == 'delay':
                self.pause(frame['duration_ms'] / 1000.0)
            else:
                raise RuntimeError('unsupported frame type: ' + kind)
        self.state = ('crouched' if mid == '002' else
                      'standing' if mid == '001' or motion.get('end_state') == STANDING
                      else 'unknown')

    pause = staticmethod(time.sleep)

    def close(self):
        self.ser.close()


def load_motion(entries, mid):
    motion = entries[mid]
    data = json.loads((MOTIONS / motion['file']).read_text(encoding='utf-8'))
    return data


class DryRunRobi(SerialRobi):
    """Exercise playback logic without opening a serial port."""
    def __init__(self, port=None):
        self.state = 'crouched'

    def send(self, command, expected, timeout=5):
        print('[dry-run] ' + command, flush=True)

    def read_done(self, timeout):
        pass

    def pause(self, seconds):
        pass

    def close(self):
        pass


def make_chat(args):
    sys.path.insert(0, str(LLM))
    from chat import Chat, load_config
    from server import Server
    config_file = Path(args.config).expanduser().resolve()
    # chat.py resolves these overrides relative to the config file.
    if args.server:
        os.environ['ROBI_LLAMA_SERVER'] = str(Path(args.server).expanduser().resolve())
    if args.model:
        os.environ['ROBI_MODEL'] = str(Path(args.model).expanduser().resolve())
    config = load_config(config_file)
    for key in ('llama_server', 'model'):
        require_file(config[key])
    if not os.access(str(config['llama_server']), os.X_OK):
        raise ValueError('llama-server is not executable: ' + str(config['llama_server']))
    config['blocked_motion_ids'] = sorted(set(config['blocked_motion_ids']) | {'001', '002', '023'})

    class MotionChat(Chat):
        def build_prompt(self, user):
            prompt, info = super().build_prompt(user)
            before = '今はテキスト試験。動作は実行されない。'
            after = '実機のRobiが立ち姿勢で会話中。適切な動作は実行される。'
            prompt = prompt.replace(before, after)
            info['prompt_chars'] = len(prompt)
            info['prompt_token_upper_bound'] = len(prompt.encode('utf-8')) + 32
            return prompt, info

    return MotionChat(config), Server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', default='/dev/ttyACM0')
    parser.add_argument('--server', help='path to existing CUDA llama-server')
    parser.add_argument('--model', help='path to existing GGUF')
    parser.add_argument('--config', default=os.environ.get('ROBI_LLM_CONFIG', str(LLM / 'config.json')))
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--dry-run', action='store_true', help='run LLM and simulate motions without serial access')
    mode.add_argument('--ping', action='store_true', help='only check ESP32 PING; no torque or motion commands')
    mode.add_argument('--check', action='store_true', help='validate files without moving or starting LLM')
    args = parser.parse_args()
    if args.ping:
        robot = SerialRobi(args.port)
        try:
            print('PING: ROBI_MOTION_V3')
        finally:
            robot.close()
        return
    chat, Server = make_chat(args)
    entries = prepare(chat.config['motion_index'])
    if args.check:
        validator = DryRunRobi()
        validator.send = lambda *a, **k: None
        for mid in entries:
            motion = load_motion(entries, mid)
            if motion.get('format') != 'robi-motion-v1':
                raise ValueError('unsupported motion format: ' + mid)
            for frame in motion['frames']:
                if frame.get('type', 'pose') == 'pose':
                    validator.frame(frame)
        print('Assets: OK, motions: {}, server: {}, model: {}'.format(
            len(entries), chat.config['llama_server'].is_file(), chat.config['model'].is_file()))
        return

    if not args.dry_run:
        print('Robi must START CROUCHED with torque OFF. Support the robot.')
        answer = input('Ready? [y/N] ').strip().lower()
        if answer not in ('y', 'yes'):
            return
    robot = DryRunRobi() if args.dry_run else SerialRobi(args.port)
    crouch_safe = False
    try:
        # Initialize the LLM server before standing, to avoid holding a standing
        # robot unmonitored while a long server startup occurs.
        with Server(chat) as llm:
            robot.play(load_motion(entries, '001'), '001')
            crouch_safe = True
            print('Ready to talk. Enter /quit to crouch and exit. (/exit is also accepted)')
            while True:
                try:
                    user = input('あなた> ').strip()
                except EOFError:
                    user = '/quit'
                if user.lower() in ('/quit', '/exit', 'exit', 'quit', '終了'):
                    break
                if not user:
                    continue
                try:
                    result = llm.infer(user)
                except Exception as exc:
                    print('[LLM ERROR] ' + str(exc), file=sys.stderr)
                    continue
                print('ロビ> ' + result['speech'])
                mid = result['motion_id']
                if mid is None:
                    continue
                item = entries.get(mid)
                if (item is None or mid in chat.blocked or
                        item.get('start_state') != STANDING or
                        item.get('end_state') != STANDING or robot.state != 'standing'):
                    print('[motion skipped] {} (not a verified stand-to-stand motion)'.format(mid))
                    continue
                try:
                    robot.play(load_motion(entries, mid), mid)
                except Exception as exc:
                    print('[MOTION ERROR] ' + str(exc), file=sys.stderr)
                    crouch_safe = False
                    break
            if crouch_safe and robot.state == 'standing':
                print('Crouching before exit...')
                robot.play(load_motion(entries, '002'), '002')
    except KeyboardInterrupt:
        print('\nInterrupted. Do not release the standing robot unexpectedly.', file=sys.stderr)
        # A pose may be incomplete; do not automatically torque off.
    finally:
        robot.close()
        print('Dry-run finished.' if args.dry_run else
              'Serial closed. If the robot remains standing, manually secure it.')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('[ERROR] ' + str(exc), file=sys.stderr)
        sys.exit(1)
