"""Heart pose extraction. RM4 control flow is intentionally not executed."""
import math
import re
from pathlib import Path
import xml.etree.ElementTree as ET

LIMITS = {i: (-150, 150) for i in range(2, 22)}
LIMITS.update({16: (-100, 100), 17: (-60, 80), 18: (0, 90)})

def signed(n):
    return n - 65536 if n >= 32768 else n

def writes(text):
    for m in re.finditer(r'<mem_w\b[^>]*(?<!/)>.*?</mem_w>', text, re.S):
        header, body = m.group().split('>', 1)
        e = ET.fromstring(header + '/>')
        body = body.rsplit('</mem_w>', 1)[0]
        body = re.sub(r'#.*', '', body)
        yield m.start(), e, [int(s.strip(), 0) for s in body.split(',') if s.strip()]

def extract(path, startup):
    text = Path(path).read_bytes().decode('cp932')
    config = Path(startup).read_bytes().decode('cp932')
    offsets = {}
    for _, e, values in writes(config):
        adr = int(e.attrib['adr'], 0)
        if 0x1040 <= adr <= 0x1500 and (adr - 0x1000) % 64 == 0:
            offsets[str((adr - 0x1000) // 64 + 1)] = signed(values[5])
    if len(offsets) != 20:
        raise ValueError('STARTUP.XML のID2〜21のOFSを読み取れません')
    period = next((v[0] for _, e, v in writes(config) if int(e.attrib['adr'], 0) == 0x40), 16667)
    all_writes = list(writes(text))
    frames = []
    for idx, (pos, e, values) in enumerate(all_writes):
        if int(e.attrib['adr'], 0) != 0xa00 or e.attrib.get('size') != '2':
            continue
        if len(values) < 42:
            raise ValueError('短い姿勢データです')
        end = next((p for p, x, _ in all_writes[idx+1:] if int(x.attrib['adr'], 0) == 0xa00), len(text))
        ticks = next((v[0] for p, x, v in all_writes[idx+1:] if p < end and int(x.attrib['adr'], 0) == 0xb00), None)
        if ticks is None:
            raise ValueError('姿勢に対応する移動時間がありません')
        names = re.findall(r'<block\b[^>]*name="([^"]*)"', text[:pos])
        frames.append({'name': names[-1] if names else f'Pose {len(frames)+1}',
                       'duration_ms': max(50, round(ticks * period / 1000)),
                       'angles': {str(i): (signed(values[(i-1)*2]) + offsets[str(i)]) / 10 for i in range(2,22)},
                       'heart_gain': {str(i): values[(i-1)*2+1] for i in range(2,22)}})
    if not frames:
        raise ValueError('0x0a00の姿勢ブロックが見つかりません')
    return {'format': 'robi-motion-v1', 'source': str(path), 'conversion': '(position + OFS) / 10',
            'offsets': offsets, 'warnings': ['ファイル順の姿勢抽出です。分岐・ジャンプ・音声・LED・ゲインは実行しません。',
                                         'OFSの補正方向と時間換算は実機未検証です。'], 'frames': frames}

def validate(data):
    if data.get('format') != 'robi-motion-v1' or not isinstance(data.get('frames'), list) or not data['frames']:
        raise ValueError('robi-motion-v1の空でないframesが必要です')
    for f in data['frames']:
        if not isinstance(f, dict): raise ValueError('各行はオブジェクトで指定してください')
        kind=f.get('type','pose')
        if kind in ('delay','audio'):
            t=f.get('duration_ms')
            if isinstance(t,bool) or not isinstance(t,(int,float)) or not math.isfinite(t):
                raise ValueError('時間は有限の数値が必要です')
            if 'angles' in f: raise ValueError('待機・音声行に角度は指定しません')
            if kind=='delay' and (not isinstance(t,int) or not 1<=t<=2147483647):
                raise ValueError('待機時間は1〜2147483647msの整数です')
            if kind=='audio':
                if t!=0: raise ValueError('音声開始行の時間は0msです')
                if not isinstance(f.get('path'),str) or not f['path'].strip():
                    raise ValueError('音声のファイルパスが必要です')
                if not isinstance(f.get('wait',False),bool): raise ValueError('音声のwaitはtrue/falseです')
            continue
        if kind=='torque':
            if not isinstance(f.get('enabled'), bool): raise ValueError('トルクのenabledはtrue/falseです')
            t=f.get('duration_ms')
            if isinstance(t,bool) or not isinstance(t,(int,float)) or t!=0:
                raise ValueError('トルク行の時間は0msです')
            if 'angles' in f: raise ValueError('トルク行に角度は指定しません')
            continue
        if kind!='pose': raise ValueError(f'未対応の動作種別: {kind}')
        t = f['duration_ms']
        if isinstance(t, bool) or not isinstance(t, (int, float)) or not math.isfinite(t) or not 50 <= t <= 163830:
            raise ValueError('時間は50〜163830msです')
        if set(f['angles']) != {str(i) for i in range(2,22)}:
            raise ValueError('ID2〜21の20軸が必要です')
        for k, v in f['angles'].items():
            if isinstance(v, bool) or not isinstance(v, (float, int)) or not math.isfinite(v):
                raise ValueError('角度は有限の数値が必要です')
    return data

def check_limits(data):
    validate(data)
    for n, f in enumerate(data['frames'], 1):
        if f.get('type','pose')!='pose': continue
        for k, v in f['angles'].items():
            lo, hi = LIMITS[int(k)]
            if not lo <= v <= hi:
                raise ValueError(f'姿勢{n} ID{k}: {v}° は範囲{lo}〜{hi}°外です')


def check_transport(data):
    """Servo position is signed 16-bit in 0.1 degree units."""
    validate(data)
    for n, f in enumerate(data['frames'], 1):
        if f.get('type','pose')!='pose': continue
        for k, v in f['angles'].items():
            if not -3276.8 <= v <= 3276.7:
                raise ValueError(f'姿勢{n} ID{k}: {v}° は通信の16ビット範囲外です')


def check_sequence(data):
    """Do not issue a move after a recorded torque OFF without an ON."""
    validate(data)
    enabled=True  # Initial torque is controlled by the existing manual button.
    for n, frame in enumerate(data['frames'],1):
        if frame.get('type')=='torque': enabled=frame['enabled']
        elif frame.get('type','pose')=='pose' and not enabled:
            raise ValueError(f'行{n}: トルクOFF後の移動にはトルクON行を追加してください')


def resolve_audio_paths(data, base_dir):
    """Normalize on import so merging and saving elsewhere preserve references."""
    import copy
    result=copy.deepcopy(validate(data))
    for frame in result['frames']:
        if frame.get('type')=='audio':
            path=Path(frame['path']).expanduser()
            if not path.is_absolute(): path=Path(base_dir)/path
            frame['path']=str(path.resolve())
    return result
