"""Shared pose snapshots. Applying them never changes playback semantics."""
import copy
import json
import uuid
from pathlib import Path
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QListWidget,
    QPushButton, QInputDialog, QDialog, QDialogButtonBox, QFormLayout,
    QLineEdit, QComboBox, QDoubleSpinBox)
from .motion import validate


def apply_boundary(data, state, side, duration):
    frames=copy.deepcopy(state['frames'])
    for frame in frames:
        frame['boundary_state']={'side':side, 'id':state['id']}
        if frame.get('type','pose')=='pose': frame['duration_ms']=duration
    validate(dict(format='robi-motion-v1',frames=frames))
    remaining=[f for f in data['frames'] if f.get('boundary_state',{}).get('side')!=side]
    data['frames']=frames+remaining if side=='start' else remaining+frames


class StateStore:
    def __init__(self, path):
        self.path=Path(path); self.states=[]; self.error=None
        if self.path.exists():
            try:
                data=json.loads(self.path.read_text(encoding='utf-8'))
                if data.get('format')!='robi-common-states-v1': raise ValueError('共通状態ファイルの形式が不正です')
                self.check(data['states']); self.states=data['states']
            except Exception as exc: self.error=str(exc)

    @staticmethod
    def check(states):
        ids=set()
        for state in states:
            if not isinstance(state['id'],str) or not state['id'] or state['id'] in ids: raise ValueError('共通状態IDが不正・重複しています')
            ids.add(state['id'])
            if not isinstance(state['name'],str) or not state['name'].strip(): raise ValueError('状態名を入力してください')
            validate(dict(format='robi-motion-v1',frames=state['frames']))
            kinds=[f.get('type','pose') for f in state['frames']]
            if kinds not in (['pose'],['torque','pose'],['torque','pose','torque']): raise ValueError('共通状態は姿勢と全軸トルク設定のみです')
            if kinds!=['pose'] and not state['frames'][0]['enabled']: raise ValueError('姿勢の前はトルクONが必要です')

    def replace(self, states):
        if self.error: raise ValueError('共通状態ファイルの読み込みエラーを解消してください: '+self.error)
        self.check(states)
        temp=self.path.with_suffix('.json.tmp')
        temp.write_text(json.dumps({'format':'robi-common-states-v1','states':states},ensure_ascii=False,indent=2),encoding='utf-8')
        temp.replace(self.path); self.states=copy.deepcopy(states)

    def get(self, state_id):
        for state in self.states:
            if state['id']==state_id: return copy.deepcopy(state)
        raise ValueError('共通状態が未登録です: '+state_id)


class StateEditor(QDialog):
    def __init__(self, state, parent):
        super().__init__(parent); self.setWindowTitle('共通状態を編集'); self.state=copy.deepcopy(state)
        layout=QVBoxLayout(self); form=QFormLayout(); layout.addLayout(form)
        self.name=QLineEdit(state['name']); form.addRow('状態名',self.name)
        self.torque=QComboBox(); self.torque.addItems(['指定なし','全軸ON','全軸OFF（姿勢へ移動後）'])
        torques=[f['enabled'] for f in state['frames'] if f.get('type')=='torque']
        self.torque.setCurrentIndex(0 if not torques else 1 if torques[-1] else 2)
        form.addRow('トルク',self.torque)
        self.pose=copy.deepcopy(next(f for f in state['frames'] if f.get('type','pose')=='pose'))
        self.angles={}
        # Two columns keep all twenty axes visible in a separate window.
        row=QHBoxLayout(); layout.addLayout(row)
        forms=[QFormLayout(),QFormLayout()]
        for f in forms: row.addLayout(f)
        for i in range(2,22):
            control=QDoubleSpinBox(); control.setDecimals(4); control.setRange(-3276.8,3276.7); control.setValue(self.pose['angles'][str(i)])
            self.angles[str(i)]=control; forms[(i-2)//10].addRow('ID'+str(i)+' °',control)
        buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); layout.addWidget(buttons)

    def result_state(self):
        self.state['name']=self.name.text()
        self.pose['angles']={k:c.value() for k,c in self.angles.items()}
        self.pose.pop('boundary_state',None)
        frames=[self.pose]
        mode=self.torque.currentIndex()
        if mode:
            frames.insert(0,dict(type='torque',name='トルクON',enabled=True,duration_ms=0))
            if mode==2: frames.append(dict(type='torque',name='トルクOFF',enabled=False,duration_ms=0))
        self.state['frames']=frames
        return self.state


class StateManager(QWidget):
    def __init__(self, editor):
        super().__init__(editor); self.setWindowFlag(Qt.Window,True)
        self.editor=editor; self.setWindowTitle('共通状態を管理'); self.resize(460,340)
        layout=QVBoxLayout(self); self.list=QListWidget(); layout.addWidget(self.list)
        row=QHBoxLayout(); layout.addLayout(row)
        for label, action in [('選択姿勢から追加',self.add),('名前変更',self.rename),('削除',self.delete),('編集',self.edit)]:
            b=QPushButton(label); b.clicked.connect(lambda checked=False,a=action:self.run(a)); row.addWidget(b)

    def refresh(self):
        selected=self.list.currentRow(); self.list.clear()
        self.list.addItems([s['name'] for s in self.editor.state_store.states]); self.list.setCurrentRow(selected)

    def run(self, action):
        try: self.editor.editable(); action()
        except Exception as exc: self.editor.error(exc)

    def commit(self, states):
        self.editor.state_store.replace(states); self.refresh(); self.editor.refresh_states()

    def current(self):
        index=self.list.currentRow()
        if index<0: raise ValueError('共通状態を選択してください')
        return index

    def add(self):
        rows=sorted({i.row() for i in self.editor.table.selectionModel().selectedRows()})
        if len(rows)!=1: raise ValueError('メイン画面の姿勢を1行選択してください')
        pose=self.editor.frame_at(rows[0])
        if pose.get('type','pose')!='pose': raise ValueError('姿勢行を選択してください')
        pose.pop('boundary_state',None)
        state=dict(id=uuid.uuid4().hex,name=pose['name'],frames=[pose])
        dialog=StateEditor(state,self)
        if dialog.exec_()==QDialog.Accepted: self.commit(self.editor.state_store.states+[dialog.result_state()])

    def rename(self):
        index=self.current(); states=copy.deepcopy(self.editor.state_store.states)
        name,ok=QInputDialog.getText(self,'名前変更','状態名',text=states[index]['name'])
        if ok: states[index]['name']=name; self.commit(states)

    def delete(self):
        index=self.current(); states=copy.deepcopy(self.editor.state_store.states); del states[index]; self.commit(states)

    def edit(self):
        index=self.current(); states=copy.deepcopy(self.editor.state_store.states)
        dialog=StateEditor(states[index],self)
        if dialog.exec_()==QDialog.Accepted: states[index]=dialog.result_state(); self.commit(states)
