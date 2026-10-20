#!/usr/bin/env python3
"""Jetson TX2: start crouched, stand, chat+motion, /quit to crouch.
Requires Python 3.6+, pyserial, an existing llama-server binary and model.
Caches trusted source files from acetaminophen34/robi/main for standalone Jetson use.
"""
import argparse
import json
import math
import os
from pathlib import Path
import sys
import time
from urllib.parse import quote
from urllib.request import urlopen

import serial

REPO = 'https://raw.githubusercontent.com/acetaminophen34/robi/main/'
ROOT = Path.home() / 'robi_runtime'
LLM = ROOT / 'jetson' / 'llm'
MOTIONS = ROOT / 'motion_editor' / 'motions'
STANDING = 'e0075cc3fa954af19e30784876243bc3'
CORE_FILES = [
    'jetson/llm/chat.py', 'jetson/llm/server.py',
    'jetson/llm/config.json', 'jetson/llm/personality.md',
    'jetson/llm/examples.json', 'motion_editor/motions/index.json',
]


def fetch(relative, refresh=False):
    dest = ROOT / relative
    if refresh or not dest.is_file():
        dest.parent.mkdir(parents=True, exist_ok=True)
        print('[download] ' + relative, flush=True)
        address = REPO + '/'.join(quote(piece) for piece in relative.split('/'))
        with urlopen(address, timeout=30) as src:
            content = src.read()
        tmp = dest.with_name(dest.name + '.tmp')
        tmp.write_bytes(content)
        tmp.replace(dest)
    return dest


def prepare(refresh=False):
    for path in CORE_FILES:
        fetch(path, refresh)
    index = json.loads((MOTIONS / 'index.json').read_text(encoding='utf-8'))
    if index.get('format') != 'robi-motion-index-v1':
        raise ValueError('invalid motion index')
    entries = {}
    for motion in index['motions']:
        mid = motion['id']
        filename = motion['file']
        if Path(filename).name != filename or not filename.endswith('.json'):
            raise ValueError('unsafe filename in index')
        entries[mid] = motion
        fetch('motion_editor/motions/' + filename, refresh)
    return entries


class SerialRobi:
    def __init__(self, port):
        self.ser = serial.Serial(port, 115200, timeout=0.2, write_timeout=2)
        time.sleep(2)
        self.ser.reset_input_buffer()
        self.send('PING', 'ROBI_MOTION_V3', 4)
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
                time.sleep(frame['duration_ms'] / 1000.0)
            else:
                raise RuntimeError('unsupported frame type: ' + kind)
        self.state = ('crouched' if mid == '002' else
                      'standing' if mid == '001' or motion.get('end_state') == STANDING
                      else 'unknown')

    def close(self):
        self.ser.close()


def load_motion(entries, mid):
    motion = entries[mid]
    data = json.loads((MOTIONS / motion['file']).read_text(encoding='utf-8'))
    return data


def find_default(name, suffix):
    candidates = [
        Path.home() / 'Projects' / 'jetson-lab' / suffix,
        Path.home() / 'jetson-lab' / suffix,
    ]
    for path in candidates:
        if path.is_file():
            return path
    return candidates[0]


def make_chat(entries, args):
    sys.path.insert(0, str(LLM))
    from chat import Chat, load_config
    from server import Server
    config_file = LLM / 'config.json'
    # chat.py resolves these overrides relative to the config file.
    os.environ['ROBI_MOTION_INDEX'] = str(MOTIONS / 'index.json')
    if args.server:
        os.environ['ROBI_LLAMA_SERVER'] = str(Path(args.server).expanduser().resolve())
    elif not os.environ.get('ROBI_LLAMA_SERVER'):
        os.environ['ROBI_LLAMA_SERVER'] = str(find_default('server', 'work/llama-cuda/build-gpu/bin/llama-server'))
    if args.model:
        os.environ['ROBI_MODEL'] = str(Path(args.model).expanduser().resolve())
    elif not os.environ.get('ROBI_MODEL'):
        os.environ['ROBI_MODEL'] = str(find_default('model', 'work/models/Qwen3-1.7B-Q4_K_M.gguf'))
    config = load_config(config_file)
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
    parser.add_argument('--refresh', action='store_true', help='redownload cached source and motions')
    parser.add_argument('--check', action='store_true', help='validate files without moving or starting LLM')
    args = parser.parse_args()
    entries = prepare(args.refresh)
    chat, Server = make_chat(entries, args)
    if args.check:
        print('Assets: OK, motions: {}, server: {}, model: {}'.format(
            len(entries), chat.config['llama_server'].is_file(), chat.config['model'].is_file()))
        return

    print('Robi must START CROUCHED with torque OFF. Support the robot.')
    answer = input('Ready? [y/N] ').strip().lower()
    if answer not in ('y', 'yes'):
        return
    robot = SerialRobi(args.port)
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
        print('Serial closed. If the robot remains standing, manually secure it.')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('[ERROR] ' + str(exc), file=sys.stderr)
        sys.exit(1)
