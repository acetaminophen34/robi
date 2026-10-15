"""Folder browser using the editor's existing hardware playback engine."""
import json
from pathlib import Path
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QListWidget, QListWidgetItem, QPlainTextEdit, QFileDialog)
from .motion import resolve_audio_paths


class MotionPlayer(QWidget):
    def __init__(self, controller):
        super().__init__(controller, Qt.Window)
        self.controller=controller; self.editors=[]
        self.folder=Path(__file__).resolve().parents[1]/'motions'
        self.setWindowTitle('Robi モーションプレーヤー'); self.resize(720,560)
        layout=QVBoxLayout(self); row=QHBoxLayout(); layout.addLayout(row)
        for title, callback in [('フォルダを開く',self.choose_folder),('更新',self.refresh)]:
            button=QPushButton(title); button.clicked.connect(callback); row.addWidget(button)
        self.folder_label=QLabel(); self.folder_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.folder_label)
        self.list=QListWidget(); layout.addWidget(self.list,2)
        self.list.currentItemChanged.connect(self.show_details)
        self.list.itemDoubleClicked.connect(lambda item:self.play_item())
        self.details=QPlainTextEdit(); self.details.setReadOnly(True); layout.addWidget(self.details,1)
        row=QHBoxLayout(); layout.addLayout(row)
        self.play_button=QPushButton('選んだモーションを再生'); self.play_button.clicked.connect(self.play_item); row.addWidget(self.play_button)
        self.edit_button=QPushButton('エディタで開く'); self.edit_button.clicked.connect(self.edit_item); row.addWidget(self.edit_button)
        stop=QPushButton('停止・トルクOFF'); stop.clicked.connect(controller.stop); row.addWidget(stop)
        self.status=QLabel(); layout.addWidget(self.status)
        layout.addWidget(QLabel('クリックで詳細表示・ダブルクリックで実機再生。接続とトルクONはメイン画面で操作。'))
        self.timer=QTimer(self); self.timer.timeout.connect(self.update_status); self.timer.start(100)
        self.refresh(); self.update_status()

    def choose_folder(self):
        path=QFileDialog.getExistingDirectory(self,'モーションフォルダ',str(self.folder))
        if path: self.folder=Path(path); self.refresh()

    def refresh(self):
        current=self.list.currentItem(); selected=current.data(Qt.UserRole) if current else None
        self.list.clear(); self.folder_label.setText(str(self.folder))
        if self.folder.is_dir():
            for path in sorted(self.folder.iterdir(),key=lambda p:p.name.casefold()):
                if not path.is_file() or path.suffix.lower()!='.json': continue
                try:
                    data=self.read(path); name=data.get('name') or path.stem
                    title=f'{name}  —  {path.name}'
                except Exception: title=f'読み込み不可  —  {path.name}'
                item=QListWidgetItem(title); item.setData(Qt.UserRole,str(path)); self.list.addItem(item)
                if str(path)==selected: self.list.setCurrentItem(item)
        if self.list.currentRow()<0 and self.list.count(): self.list.setCurrentRow(0)
        if not self.list.count(): self.details.setPlainText('このフォルダにモーションJSONがありません。')
        self.update_status()

    @staticmethod
    def read(path):
        path=Path(path)
        return resolve_audio_paths(json.loads(path.read_text(encoding='utf-8')),path.parent)

    def selected_path(self):
        item=self.list.currentItem()
        if item is None: raise ValueError('モーションを選択してください')
        return Path(item.data(Qt.UserRole))

    def state_name(self, value):
        if not value: return '指定なし'
        for state in self.controller.state_store.states:
            if state['id']==value: return state['name']
        return '未登録: '+value

    def show_details(self, *args):
        try:
            path=self.selected_path(); data=self.read(path)
            frames=data['frames']; duration=sum(f['duration_ms'] for f in frames)/1000
            self.details.setPlainText('\n'.join([
                'モーション名: '+(data.get('name') or path.stem),
                '動作説明: '+(data.get('description') or '未記入'),
                f'フレーム数: {len(frames)} / 移動・待機時間: {duration:g} 秒（音声時間は別）',
                '開始状態: '+self.state_name(data.get('start_state')),
                '終了状態: '+self.state_name(data.get('end_state')), 'ファイル: '+str(path)]))
        except Exception as exc: self.details.setPlainText(str(exc))

    def play_item(self):
        try:
            # Playback reads a fresh snapshot without replacing the current editing table.
            self.controller.editable()
            self.controller.play_motion(self.read(self.selected_path()))
            self.update_status()
        except Exception as exc: self.controller.error(exc)

    def edit_item(self):
        try:
            data=self.read(self.selected_path())
            from robi_gui import Window
            editor=Window(); editor.load(data); editor.setWindowTitle('Robi モーションエディタ — '+self.selected_path().name)
            self.editors.append(editor); editor.show()
        except Exception as exc: self.controller.error(exc)

    def update_status(self):
        c=self.controller
        status='再生中' if c.playing else '操作完了待ち' if c.pending else '接続済み' if c.ready else '未接続'
        self.status.setText(status)
        self.play_button.setEnabled(self.list.currentItem() is not None and not c.playing and not c.pending)
        self.edit_button.setEnabled(self.list.currentItem() is not None)

    def closeEvent(self, event):
        for editor in self.editors: editor.close()
        event.accept()
