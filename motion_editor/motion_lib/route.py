"""Resolve RM4 byte-address jumps. Conditions are chosen, not emulated."""
import copy
import re
from pathlib import Path
import xml.etree.ElementTree as ET
from .motion import extract

# Parse bytes so CP932 Japanese and CRLF do not change jump addresses.
TOKENS = re.compile(rb'<medit\b[^>]*>.*?</medit>|<calc\b[^>]*>.*?</calc>|<mem_w\b[^>]*(?<!/)>.*?</mem_w>|<\w+\b[^>]*?/>', re.S)

class RouteCancelled(Exception): pass

class Program:
    def __init__(self,path,startup):
        self.path=Path(path).resolve()
        self.raw=self.path.read_bytes()
        self.tokens=list(TOKENS.finditer(self.raw))
        self.address={m.start():i for i,m in enumerate(self.tokens)}
        self.names={}; name='開始'
        for i,m in enumerate(self.tokens):
            text=m.group().decode('cp932')
            if text.startswith('<medit'):
                found=re.search(r'<block\b[^>]*name="([^"]*)"',text)
                if found: name=found[1] or '開始'
            self.names[i]=name
        # Extraction remains in file order; associate each pose with its byte address.
        positions=[m.start() for m in self.tokens if re.match(rb'<mem_w\b',m.group())
                   and re.search(rb'adr="0x0[aA]00"',m.group())]
        try: self.data=extract(self.path,startup)
        except ValueError as e:
            if str(e)!='0x0a00の姿勢ブロックが見つかりません': raise
            self.data=None
        self.frames=dict(zip(positions,self.data['frames'])) if self.data else {}

    def target(self,adr):
        if adr not in self.address:
            raise ValueError(f'{self.path.name}: 未対応のジャンプ先0x{adr:x}。実行順は生成しません')
        return self.address[adr]

    def label(self,adr):
        return self.names[self.target(adr)]

def resolve(path,startup,choose,root=None,max_steps=10000,max_frames=2000):
    """choose(context) -> jump/next/end, or None to cancel. No hardware IO."""
    path=Path(path).resolve(); startup=Path(startup).resolve()
    root=Path(root or path.parent).resolve()
    cache={}; frames=[]; decisions=[]; notices=set(); visits={}; stack=[]
    def program(p):
        if p not in cache: cache[p]=Program(p,startup)
        return cache[p]
    current=program(path); pc=0; base=current.data
    for step in range(max_steps):
        if pc>=len(current.tokens):
            if stack: current,pc=stack.pop(); continue
            break
        m=current.tokens[pc]; text=m.group().decode('cp932'); pc+=1
        tag=re.match(r'<(\w+)',text)[1]
        if tag=='medit': continue
        if m.start() in current.frames:
            f=copy.deepcopy(current.frames[m.start()])
            f['source_file']=str(current.path);f['source_address']=m.start()
            frames.append(f)
            if base is None: base=current.data
            if len(frames)>=max_frames:
                raise ValueError('姿勢数上限。ループの終了経路を選んでください')
        elif tag=='jump':
            current_pc=current.target(int(ET.fromstring(text).attrib['adr'],0))
            key=(current.path,current_pc);visits[key]=visits.get(key,0)+1
            if visits[key]>100: raise ValueError('同じジャンプを100回超えました。ループの終了経路を選んでください')
            pc=current_pc
        elif tag=='calc':
            jumps=re.findall(r'<jump\b[^>]*adr="([^"]+)"[^>]*/>',text)
            if not jumps:
                notices.add('変数計算・書き込みは評価せず、条件経路を手動選択しています。');continue
            if len(jumps)!=1: raise ValueError('複数ジャンプを含む条件式には未対応です')
            adr=int(jumps[0],0)
            next_label=current.names.get(pc,'終了')
            if pc<len(current.tokens):
                next_text=current.tokens[pc].group().decode('cp932')
                if next_text.startswith('<jump'):
                    next_label=current.label(int(ET.fromstring(next_text).attrib['adr'],0))
            context={'file':current.path.name,'block':current.names[pc-1],
                     'jump':current.label(adr),'next':next_label,
                     'expression':text,'frames':len(frames)}
            answer=choose(context)
            if answer is None: raise RouteCancelled()
            if answer not in ('jump','next','end'): raise ValueError('不明な経路選択')
            decisions.append(dict(context,choice=answer))
            if answer=='end':
                notices.add('ユーザーが指定した分岐位置で経路を終了しました。');break
            if answer=='jump': pc=current.target(adr)
        elif tag=='call':
            filename=ET.fromstring(text).attrib['filename'].replace('\\','/')
            candidates=[(current.path.parent/filename).resolve(),(root/filename).resolve()]
            dest=next((p for p in candidates if p.is_relative_to(root) and p.is_file()),None)
            if dest is None: raise ValueError(f'呼び出し先が見つかりません: {filename}')
            if len(stack)>=32: raise ValueError('呼び出しが深すぎます')
            stack.append((current,pc));current=program(dest);pc=0
        elif tag=='return':
            if not stack: break
            current,pc=stack.pop()
        elif tag=='wait':
            adr=int(ET.fromstring(text).attrib.get('adr','0'),0)
            if adr!=0xb43:
                notices.add(f'外部状態待ち0x{adr:x}は再現せず、省略しています。')
        elif tag in ('play','servoenable'):
            notices.add('音声・サーボ有効軸の切替・ゲインは再現していません。')
        elif tag=='mem_w':
            # Writes other than pose/time are not part of the motion-only player.
            pass
        else:
            raise ValueError(f'未対応の命令: {tag}。実行順は生成しません')
    else: raise ValueError('実行ステップ上限。ループの終了経路を選んでください')
    if not frames or base is None: raise ValueError('選んだ経路には姿勢がありません')
    data=copy.deepcopy(base);data['frames']=frames;data['source']=str(path)
    data['route_choices']=decisions;data['execution_order']='resolved-jumps-manual-conditions'
    data['warnings']=['ジャンプ・呼び出しをたどった実行順です。条件はユーザー選択で実機状態を評価しません。',
                      'OFS・時間換算・補間は実機未検証です。']+sorted(notices)
    return data
