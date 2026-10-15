"""Run: python3 esp/gui_motion/robi_gui.py"""
import copy
import json
import sys
import time
from pathlib import Path
import serial
import serial.tools.list_ports
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtWidgets import QApplication, QWidget, QFileDialog, QTableWidgetItem, QMessageBox
from motion_lib.motion import extract, validate, check_limits, check_transport, check_sequence, resolve_audio_paths

ROOT = Path(__file__).resolve().parents[2]

class Window(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Robi モーションエディタ')
        self.resize(1100, 720)
        self.data = None
        self.preview = None
        self.link = None
        self.ready = False
        self.playing = False
        self.pending = None
        self.can_capture = False
        self.capture_angles = {}
        self.rx = bytearray()
        self.index = 0
        self.audio=None
        self.delay_timer=QTimer(self); self.delay_timer.setSingleShot(True)
        self.delay_timer.timeout.connect(self.delay_finished)
        from motion_lib.editor_ui import build, refresh_status
        build(self)
        self.timer=QTimer(self); self.timer.timeout.connect(self.poll); self.timer.start(20)
        self.timer.timeout.connect(lambda: refresh_status(self))
        self.ports()

    def open_preview(self):
        if self.preview is None:
            from motion_lib.preview import Preview
            self.preview=Preview(self)
            self.preview.destroyed.connect(self.preview_closed)
        self.preview.show()
        self.preview.raise_()
        self.preview.activateWindow()
        return self.preview

    def preview_closed(self, *args):
        self.preview=None

    def play_preview(self):
        try:
            data=self.selected()
            self.open_preview().play(data)
        except Exception as e: self.error(e)

    def show_axis_report(self):
        from motion_lib.axis_signs import report
        try:
            box=QMessageBox(self)
            box.setWindowTitle('Heartから推定した軸の正負')
            box.setText('左右の対応から3D表示の正負を推定しています。絶対方向は未校正です。')
            box.setDetailedText(report(ROOT/'Robi-heart'))
            box.exec_()
        except Exception as e: self.error(e)

    def error(self, exc):
        QMessageBox.warning(self, '確認', str(exc))

    def ports(self):
        self.port.clear()
        self.port.addItems([p.device for p in serial.tools.list_ports.comports()])

    def connect(self):
        if self.link:
            self.stop(); self.link.close(); self.link=None; self.ready=False
            return
        try:
            self.link=serial.Serial(self.port.currentText(),115200,timeout=0,write_timeout=0.2)
            self.rx.clear(); self.ready=False; self.can_capture=False
            self.link.write(b'PING\n')
            self.log.appendPlainText('接続確認中')
        except Exception as e:
            self.link=None; self.error(e)

    def send(self, command):
        if not self.link or not self.ready:
            self.error('対応inoとの接続確認が必要です'); return False
        if self.pending:
            self.error('前の操作の完了を待ってください'); return False
        try:
            self.link.write((command+'\n').encode('ascii'))
            self.pending_torque=command=='TORQUE,1'
            self.pending='FRAME' if command.startswith('FRAME_RAW,') else command.split(',')[0]
            self.deadline=time.monotonic()+ (float(command.split(',')[1])/1000+3 if self.pending=='FRAME' else 6 if self.pending=='READ_ALL' else 3)
            return True
        except Exception as e:
            self.playing=False; self.error(e); return False

    def stop(self):
        self.playing=False; self.pending=None
        self.delay_timer.stop()
        if self.audio is not None: self.audio.stop()
        if self.link and self.ready:
            try:
                self.link.write(b'STOP\n'); self.pending='STOP'; self.deadline=time.monotonic()+3
            except Exception as e: self.error(e)

    def poll(self):
        if not self.link: return
        try:
            self.rx.extend(self.link.read(self.link.in_waiting))
            while b'\n' in self.rx:
                raw, _, rest=self.rx.partition(b'\n'); self.rx=bytearray(rest)
                text=raw.decode('ascii',errors='replace').strip(); self.log.appendPlainText(text)
                if text in ('ROBI_MOTION_V2','ROBI_MOTION_V3'):
                    self.ready=True; self.can_capture=text=='ROBI_MOTION_V3'
                elif text.startswith('POSE,') and self.pending=='READ_ALL':
                    fields=text.split(',')
                    if len(fields)!=3 or int(fields[1]) not in range(2,22):
                        raise ValueError('不正な姿勢応答です')
                    key=fields[1]
                    if key in self.capture_angles: raise ValueError('姿勢応答のIDが重複しています')
                    self.capture_angles[key]=float(fields[2])
                elif text=='DONE,READ_ALL' and self.pending=='READ_ALL':
                    self.pending=None
                    frame=dict(self.capture_frame, angles=dict(self.capture_angles))
                    try:
                        validate({'format':'robi-motion-v1','frames':[frame]})
                        self.add_frames([frame])
                    except Exception as e: self.error(e)
                elif text=='ROBI_MOTION_V1':
                    self.ready=False
                    self.log.appendPlainText('古いinoです。robi_motion.inoを書き直してください')
                elif text.startswith('ERR,'):
                    self.log.appendPlainText('実機エラー: 再生を停止します'); self.stop()
                elif text=='DONE,FRAME' and self.pending=='FRAME':
                    self.pending=None
                    if self.playing:
                        self.index+=1; self.next_frame()
                elif (text==f'OK,{self.pending}' and self.pending not in ('FRAME','READ_ALL')) or (
                        text=='OK,STOP' and self.pending=='TORQUE' and not self.pending_torque):
                    completed=self.pending; self.pending=None
                    if self.playing and completed=='TORQUE':
                        self.index+=1; self.next_frame()
            if self.pending in ('FRAME','TORQUE','STOP','READ_ALL') and time.monotonic()>self.deadline:
                if self.pending=='STOP':
                    self.pending=None; self.ready=False
                    self.log.appendPlainText('停止応答なし。接続と実機を確認してください')
                else:
                    self.log.appendPlainText('応答タイムアウト: 停止します'); self.stop()
        except Exception as e:
            self.delay_timer.stop()
            if self.audio is not None: self.audio.stop()
            self.playing=False; self.pending=None; self.ready=False
            self.link.close(); self.link=None; self.log.appendPlainText(str(e))

    def load(self,data):
        if self.playing: raise ValueError('停止してから読み込んでください')
        validate(data); self.data=copy.deepcopy(data); self.table.setRowCount(len(data['frames']))
        for row, f in enumerate(data['frames']):
            kind=f.get('type','pose')
            values=[f['name'],f['duration_ms']]+([f['angles'][str(i)] for i in range(2,22)] if kind=='pose' else ['']*20)
            label={'pose':'姿勢','delay':'待機','audio':'音声再生'}.get(kind)
            if kind=='torque': label='トルクON' if f['enabled'] else 'トルクOFF'
            values.extend([label,f.get('path',''),''])
            for col, value in enumerate(values):
                item=QTableWidgetItem(str(value))
                editable=col==0 or (col==1 and kind in ('pose','delay')) or (2<=col<=21 and kind=='pose') or (col==23 and kind=='audio')
                if not editable: item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                if col==24 and kind=='audio':
                    item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                    item.setCheckState(Qt.Checked if f.get('wait',False) else Qt.Unchecked)
                self.table.setItem(row,col,item)
        self.table.resizeColumnsToContents()
        self.log.appendPlainText('\n'.join(data.get('warnings', [])))
        self.log.appendPlainText(f"{len(data['frames'])}姿勢を読み込みました")

    def choose_route(self, context):
        box=QMessageBox(self)
        box.setWindowTitle('Heartの条件分岐を選択')
        box.setText(f"{context['file']}\n{context['block']}\nここまで{context['frames']}姿勢。実機の条件は判定できないため、進む経路を選んでください。")
        jump=box.addButton('ジャンプ先: '+context['jump'],QMessageBox.ActionRole)
        next_button=box.addButton('次へ: '+context['next'],QMessageBox.ActionRole)
        end=box.addButton('ここまでで終了',QMessageBox.AcceptRole)
        box.addButton(QMessageBox.Cancel)
        box.setDetailedText(context['expression'])
        box.exec_()
        chosen=box.clickedButton()
        return 'jump' if chosen is jump else 'next' if chosen is next_button else 'end' if chosen is end else None

    def open_raw_rm4(self):
        self.open_rm4(raw=True)

    def open_rm4(self, checked=False, raw=False):
        if self.playing:
            self.error('実機再生を停止してから読み込んでください'); return
        path,_=QFileDialog.getOpenFileName(self,'HeartのRM4',str(ROOT/'Robi-heart'),'Motion (*.RM4 *.rm4)')
        if not path: return
        startup=ROOT/'Robi-heart'/'STARTUP.XML'
        if not startup.exists():
            p,_=QFileDialog.getOpenFileName(self,'STARTUP.XMLを選択','','XML (*.XML *.xml)')
            if not p: return
            startup=Path(p)
        from motion_lib.route import resolve, RouteCancelled
        try:
            if raw:
                data=extract(path,startup)
            else:
                data=resolve(path,startup,self.choose_route,root=Path(startup).parent)
            self.import_data(data)
        except RouteCancelled: pass
        except Exception as e: self.error(e)

    def open_json(self):
        p,_=QFileDialog.getOpenFileName(self,'モーションJSON','','JSON (*.json)')
        if p:
            try: self.import_data(json.loads(Path(p).read_text(encoding='utf-8')),Path(p).resolve().parent)
            except Exception as e: self.error(e)

    def editable(self):
        if self.playing or self.pending:
            raise ValueError('通信・再生が完了してから編集してください')

    def frame_at(self, row):
        frame=copy.deepcopy(self.data['frames'][row])
        frame['name']=self.table.item(row,0).text()
        kind=frame.get('type','pose')
        if kind=='delay':
            value=float(self.table.item(row,1).text())
            frame['duration_ms']=int(value) if value.is_integer() else value
        elif kind=='audio':
            frame['path']=str(Path(self.table.item(row,23).text()).expanduser().resolve()) if self.table.item(row,23).text().strip() else ''
            frame['wait']=self.table.item(row,24).checkState()==Qt.Checked
        elif kind=='pose':
            frame.update(duration_ms=float(self.table.item(row,1).text()),
                         angles={str(i):float(self.table.item(row,i).text()) for i in range(2,22)})
        return frame

    def insert_action(self, frame):
        self.editable()
        data=self.all_data() if self.data else {'format':'robi-motion-v1','frames':[]}
        rows=[i.row() for i in self.table.selectionModel().selectedRows()]
        position=max(rows)+1 if rows else len(data['frames'])
        data['frames'].insert(position,frame)
        self.load(data); self.table.selectRow(position)

    def record_torque(self, enabled):
        try:
            self.insert_action({'type':'torque', 'name':'トルクON' if enabled else 'トルクOFF',
                                'enabled':enabled, 'duration_ms':0})
        except Exception as e: self.error(e)

    def record_delay(self):
        try: self.insert_action({'type':'delay','name':'待機','duration_ms':self.delay_time.value()})
        except Exception as e: self.error(e)

    def choose_audio(self):
        path,_=QFileDialog.getOpenFileName(self,'PC上の音声ファイル','','音声 (*.wav *.mp3 *.m4a *.ogg *.flac);;すべてのファイル (*)')
        if path: self.audio_path.setText(path)

    def record_audio(self):
        try:
            if not self.audio_path.text().strip(): raise ValueError('音声ファイルのパスを指定してください')
            path=Path(self.audio_path.text()).expanduser().resolve()
            if not path.is_file(): raise ValueError(f'音声ファイルが見つかりません: {path}')
            self.insert_action({'type':'audio','name':path.name,'path':str(path),
                                'wait':self.audio_wait.isChecked(),'duration_ms':0})
        except Exception as e: self.error(e)

    def all_data(self):
        if not self.data: raise ValueError('姿勢がありません')
        data=copy.deepcopy(self.data); data['frames']=[]
        for r in range(self.table.rowCount()):
            data['frames'].append(self.frame_at(r))
        return validate(data)

    def new_motion(self):
        try:
            self.editable(); self.data=None; self.table.setRowCount(0)
        except Exception as e: self.error(e)

    def add_frames(self, frames):
        self.editable()
        data=self.all_data() if self.data else {'format':'robi-motion-v1','frames':[]}
        data['frames'].extend(copy.deepcopy(frames)); self.load(data)
        self.table.selectRow(len(data['frames'])-1)

    def import_data(self, data, base_dir=None):
        self.editable(); data=resolve_audio_paths(data,base_dir or Path.cwd())
        if self.data:
            merged=self.all_data()
            rows=[i.row() for i in self.table.selectionModel().selectedRows()]
            position=len(merged['frames']) if self.append_import.isChecked() or not rows else max(rows)+1
            merged['frames'][position:position]=copy.deepcopy(data['frames'])
            merged.setdefault('warnings',[]).extend(data.get('warnings',[]))
            self.load(merged)
        else: self.load(data)

    def capture_pose(self):
        try:
            self.editable()
            if not self.can_capture: raise ValueError('現在角度の記録にはROBI_MOTION_V3のinoへの書き換えと接続が必要です')
            if self.data: self.all_data()
            self.capture_angles={}
            self.capture_frame={'name':self.pose_name.text(), 'duration_ms':self.pose_time.value()}
            self.send('READ_ALL')
        except Exception as e: self.error(e)

    def edit_rows(self, operation):
        try:
            self.editable(); data=self.all_data()
            rows=sorted({i.row() for i in self.table.selectionModel().selectedRows()})
            if not rows: raise ValueError('行を選択してください')
            frames=data['frames']
            if operation=='duplicate':
                for r in reversed(rows): frames.insert(r+1,copy.deepcopy(frames[r]))
                chosen=[r+1+n for n,r in enumerate(rows)]
            elif operation=='delete':
                for r in reversed(rows): del frames[r]
                chosen=[]
            else:
                if (operation==-1 and rows[0]==0) or (operation==1 and rows[-1]==len(frames)-1): return
                for r in rows if operation==-1 else reversed(rows):
                    frames[r],frames[r+operation]=frames[r+operation],frames[r]
                chosen=[r+operation for r in rows]
            if frames:
                self.load(data); self.table.clearSelection()
                from PyQt5.QtCore import QItemSelectionModel
                for r in chosen:
                    self.table.selectionModel().select(self.table.model().index(r,0),QItemSelectionModel.Select|QItemSelectionModel.Rows)
            else: self.new_motion()
        except Exception as e: self.error(e)

    def duplicate_rows(self): self.edit_rows('duplicate')
    def delete_rows(self): self.edit_rows('delete')
    def move_rows(self, direction): self.edit_rows(direction)

    def save_all(self):
        try:
            data=self.all_data()
            p,_=QFileDialog.getSaveFileName(self,'モーション全体をJSON保存','motion.json','JSON (*.json)')
            if p: Path(p).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
        except Exception as e: self.error(e)

    def selected(self):
        if not self.data: raise ValueError('モーションを開いてください')
        rows=sorted({i.row() for i in self.table.selectionModel().selectedRows()})
        if not rows: raise ValueError('保存・再生する行を選択してください')
        data=copy.deepcopy(self.data); data['frames']=[]
        for r in rows:
            data['frames'].append(self.frame_at(r))
        return validate(data)

    def save(self):
        try:
            data=self.selected()
            p,_=QFileDialog.getSaveFileName(self,'選択行のJSON保存','motion.json','JSON (*.json)')
            if p: Path(p).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
        except Exception as e: self.error(e)

    def play(self):
        try:
            if self.playing or self.pending: raise ValueError('前の操作の完了を待ってください')
            self.sequence=self.selected(); check_transport(self.sequence); check_sequence(self.sequence)
            self.raw_mode=self.ignore_limits.isChecked()
            if not self.raw_mode: check_limits(self.sequence)
            if not self.link or not self.ready: raise ValueError('対応inoに接続してください')
            self.sequence=resolve_audio_paths(self.sequence,Path.cwd())
            audio_frames=[f for f in self.sequence['frames'] if f.get('type')=='audio']
            for f in audio_frames:
                if not Path(f['path']).is_file(): raise ValueError(f"音声ファイルが見つかりません: {f['path']}")
            if audio_frames: self.ensure_audio()
            self.delay_timer.stop()
            if self.audio is not None: self.audio.stop()
            self.index=0; self.playing=True; self.next_frame()
        except Exception as e: self.error(e)

    def ensure_audio(self):
        if self.audio is None:
            from motion_lib.audio import AudioPlayer
            self.audio=AudioPlayer(self)
            self.audio.finished.connect(self.audio_finished)
            self.audio.failed.connect(self.audio_failed)
        return self.audio

    def delay_finished(self):
        if self.playing and self.pending=='DELAY':
            self.pending=None; self.index+=1; self.next_frame()

    def audio_finished(self):
        if not self.playing: return
        if self.pending=='AUDIO':
            self.pending=None; self.index+=1; self.next_frame()
        elif self.pending=='AUDIO_END':
            self.pending=None; self.next_frame()

    def audio_failed(self, message):
        if not self.playing: return
        self.stop(); self.log.appendPlainText(message); self.error(message)

    def next_frame(self):
        try:
            while self.playing:
                if self.index>=len(self.sequence['frames']):
                    if self.audio is not None and self.audio.active:
                        self.pending='AUDIO_END'; return
                    self.playing=False; self.log.appendPlainText('再生完了（最後のトルク状態を維持）'); return
                f=self.sequence['frames'][self.index]; kind=f.get('type','pose')
                self.table.clearSelection()
                if kind=='delay':
                    self.pending='DELAY'; self.delay_timer.start(f['duration_ms']); return
                if kind=='audio':
                    if f.get('wait',False): self.pending='AUDIO'
                    self.ensure_audio().start(f['path'])
                    if not self.playing: return
                    if f.get('wait',False): return
                    self.index+=1; continue
                if kind=='torque':
                    command='TORQUE,1' if f['enabled'] else 'TORQUE,0'
                else:
                    command=('FRAME_RAW,' if self.raw_mode else 'FRAME,')+str(round(f['duration_ms']))+','+','.join(str(f['angles'][str(i)]) for i in range(2,22))
                if not self.send(command): self.stop()
                return
        except Exception as e:
            self.stop(); self.error(e)

    def closeEvent(self,event):
        if self.preview is not None: self.preview.close()
        self.stop()
        if self.link: self.link.close()
        event.accept()

if __name__=='__main__':
    app=QApplication(sys.argv); window=Window(); window.show(); sys.exit(app.exec_())
