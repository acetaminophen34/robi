"""Optional 3D preview. Imported only when the preview is opened."""
import bisect
import copy
import time
from types import SimpleNamespace
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QPainter, QColor
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                            QSlider, QComboBox)
from .model_view import PoseView, ROBI_REFERENCE_POSES
from .motion import validate

REFERENCE = ROBI_REFERENCE_POSES['立ちポーズ正面~~']

class Value:
    def __init__(self, value): self.number=value
    def value(self): return self.number
    def setValue(self, value): self.number=value

class PreviewView(PoseView):
    # Dragging changes only the camera. Motion angles come from the timeline.
    def mousePressEvent(self, event):
        if event.button()==Qt.LeftButton:
            self.drag_origin=event.pos(); self.drag_joint=None

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.fillRect(0,self.height()-36,self.width(),36,QColor('#17212e'))
        painter.setPen(Qt.white)
        painter.drawText(16,self.height()-15,'ドラッグ: 視点回転  |  モーションプレビュー（実機へ送信しません）')

class Preview(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setWindowTitle('Robi 3D モーションプレビュー')
        self.resize(820,820)
        self.frames=[]; self.ends=[]; self.position=0.; self.running=False
        controls=[SimpleNamespace(id=i, angle=Value(REFERENCE[i])) for i in range(2,22)]
        self.view=PreviewView(controls)
        layout=QVBoxLayout(self)
        layout.addWidget(QLabel('全身20軸の概略モデル。関節の正負・寸法は未校正で、実機の接地や衝突は判定しません。'))
        layout.addWidget(self.view,1)
        self.status=QLabel('GUIで行を選択し「選択行を3Dで再生」を押してください'); layout.addWidget(self.status)
        self.slider=QSlider(Qt.Horizontal); self.slider.setRange(0,10000)
        self.slider.valueChanged.connect(self.seek); layout.addWidget(self.slider)
        row=QHBoxLayout(); layout.addLayout(row)
        for text, cb in [('再生／一時停止',self.toggle),('先頭へ',self.rewind),('正面',lambda:self.camera(0,12)),('横',lambda:self.camera(90,12))]:
            button=QPushButton(text); button.clicked.connect(cb); row.addWidget(button)
        self.speed=QComboBox(); self.speed.addItems(['0.25×','0.5×','1×','2×']); self.speed.setCurrentIndex(2); row.addWidget(self.speed)
        self.timer=QTimer(self); self.timer.setInterval(50); self.timer.timeout.connect(self.tick)

    def camera(self,yaw,pitch):
        self.view.yaw=yaw; self.view.pitch=pitch; self.view.update()

    def play(self, data):
        validate(data)
        self.frames=copy.deepcopy(data['frames'])
        self.ends=[]; self.targets=[]; total=0.
        target={str(i):REFERENCE[i] for i in range(2,22)}
        for f in self.frames:
            if f.get('type','pose')=='pose': target=f['angles']
            self.targets.append(dict(target))
            total+=f['duration_ms']/1000; self.ends.append(total)
        self.position=0.; self.render(); self.resume()


    def resume(self):
        if not self.frames: return
        self.running=True; self.last=time.monotonic(); self.timer.start()

    def pause(self):
        self.running=False; self.timer.stop()

    def toggle(self):
        if self.running: self.pause()
        else:
            if self.ends and self.position>=self.ends[-1]: self.position=0.
            self.resume()

    def rewind(self):
        self.pause(); self.position=0.; self.render()

    def seek(self, value):
        if not self.ends: return
        self.position=value/10000*self.ends[-1]
        self.last=time.monotonic(); self.render()

    def tick(self):
        if not self.isVisible(): self.pause(); return
        now=time.monotonic()
        self.position=min(self.ends[-1],self.position+(now-self.last)*[.25,.5,1.,2.][self.speed.currentIndex()])
        self.last=now; self.render()
        if self.position>=self.ends[-1]: self.pause()

    def render(self):
        if not self.frames: return
        idx=min(bisect.bisect_right(self.ends,self.position),len(self.frames)-1)
        start=self.ends[idx-1] if idx else 0.
        duration=self.ends[idx]-start
        fraction=max(0.,min(1.,(self.position-start)/duration)) if duration else 1.
        prev=self.targets[idx-1] if idx else {str(i):REFERENCE[i] for i in range(2,22)}
        target=self.targets[idx]
        for i,c in self.view.controls.items():
            c.angle.setValue(prev[str(i)]+(target[str(i)]-prev[str(i)])*fraction)
        self.view.update()
        self.slider.blockSignals(True); self.slider.setValue(round(self.position/self.ends[-1]*10000) if self.ends[-1] else 0); self.slider.blockSignals(False)
        torque='ON（開始時の想定）'
        for frame in self.frames[:idx+1]:
            if frame.get('type')=='torque': torque='ON' if frame['enabled'] else 'OFF'
        self.status.setText(f"{idx+1}/{len(self.frames)}  {self.frames[idx]['name']}  |  {self.position:.2f} / {self.ends[-1]:.2f} 秒  |  トルク{torque}（脱力後の姿勢変化は再現しません）")

        if any(f.get('type')=='audio' for f in self.frames):
            self.status.setText(self.status.text()+' | 音声は3Dでは再生しません（終了待ち時間は未反映）')

    def hideEvent(self,event):
        self.pause(); super().hideEvent(event)

    def closeEvent(self,event):
        self.pause(); super().closeEvent(event)
