"""棒人間で姿勢を編集する試作GUI。実行: python3 pose_gui.py"""
import math
import sys
from collections import deque

import serial
from PyQt5.QtCore import QPointF, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QColor, QPainter, QPen, QPolygonF
from PyQt5.QtWidgets import QApplication, QHBoxLayout, QLabel, QPushButton, QSlider, QWidget, QComboBox, QCheckBox, QDoubleSpinBox

from gui_test import RobiGUI, SERVOS


def matmul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def rotation(axis, degrees):
    c, s = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))
    if axis == 'x':
        return [[1, 0, 0], [0, c, -s], [0, s, c]]
    if axis == 'y':
        return [[c, 0, s], [0, 1, 0], [-s, 0, c]]
    return [[c, -s, 0], [s, c, 0], [0, 0, 1]]


def advance(point, frame, offset):
    return tuple(point[i] + sum(frame[i][j] * offset[j] for j in range(3)) for i in range(3))


class PoseView(QWidget):
    selected = pyqtSignal(int)

    def __init__(self, controls):
        super().__init__()
        self.controls = {c.id: c for c in controls}
        self.active = 16
        self.yaw = 30
        self.pitch = 12
        self.hits = []
        self.drag_origin = None
        self.reverse = {i: False for i in self.controls}
        self.reverse[17] = True
        self.zero = {i: 0.0 for i in self.controls}
        self._scene_key = None
        self._scene_cache = None
        self._camera_key = None
        self._camera_frame = None
        self.setMinimumSize(450, 430)

    def scene(self):
        # x: robot left, y: up, z: forward. Dimensions are illustrative.
        # Movement roles: https://arutora.com/4105 and /4189.
        # Signs below are a display convention, NOT verified servo polarity.
        angles = {i: (c.angle.value() - self.zero[i]) * (-1 if self.reverse[i] else 1)
                  for i, c in self.controls.items()}
        key = tuple(angles.items())
        if key == self._scene_key:
            return self._scene_cache
        faces, joints = [], []

        def box(center, frame, size, color):
            vertices = [advance(center, frame, (x * size[0]/2, y * size[1]/2, z * size[2]/2))
                        for x, y, z in [(-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),
                                        (-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1)]]
            for indices, shade in [((0,1,2,3),.60),((4,5,6,7),1.0),((0,4,7,3),.75),
                                   ((1,5,6,2),.85),((3,2,6,7),1.15),((0,1,5,4),.55)]:
                # Subdivide surfaces to keep small facial details visible in depth sorting.
                corners = [vertices[i] for i in indices]
                def surface(u,v):
                    return tuple((1-u)*(1-v)*corners[0][k] + u*(1-v)*corners[1][k]
                                 + u*v*corners[2][k] + (1-u)*v*corners[3][k] for k in range(3))
                # Keep large shells subdivided so their rear faces do not hide details.
                steps = 6 if size[0] >= .5 else 1
                for row in range(steps):
                    for col in range(steps):
                        u,v = row/steps,col/steps
                        faces.append(([surface(u,v),surface(u+1/steps,v),
                                       surface(u+1/steps,v+1/steps),surface(u,v+1/steps)],
                                      QColor(color).lighter(int(shade*100))))

        def joint(i, point, frame, axis, sign=1):
            joints.append((i, point, frame, axis))
            return matmul(frame, rotation(axis, sign * angles[i]))

        base = (0, -.65, 0)
        torso = joint(12, base, rotation('y', 0), 'y')
        box(base, rotation('y', 0), (.75,.15,.55), '#56677d')
        chest = advance(base, torso, (0,.57,0))
        box(chest, torso, (1.05,1.0,.52), '#d2dce9')
        box(advance(chest, torso, (0,.1,.28)), torso, (.52,.38,.08), '#294459')
        box(advance(chest, torso, (0,.1,.34)), torso, (.28,.07,.04), '#52e0c2')
        neck = advance(base, torso, (0,1.16,0))
        nf = joint(13, neck, torso, 'y')
        neck2 = advance(neck, nf, (0,.09,0))
        nf = joint(14, neck2, nf, 'z')
        neck3 = advance(neck2, nf, (0,.09,0))
        nf = joint(15, neck3, nf, 'x')
        head = advance(neck3, nf, (0,.34,0))
        box(head, nf, (.86,.65,.62), '#eef2f7')
        box(advance(head,nf,(0,0,.33)), nf, (.72,.39,.07), '#223449')
        for x in [-.20,.20]:
            box(advance(head,nf,(x,.04,.38)), nf, (.13,.10,.05), '#62e6e5')
        box(advance(head,nf,(0,-.12,.39)), nf, (.20,.04,.05), '#edb15d')
        for sign, arm, color in [(-1,16,'#f3a35a'),(1,19,'#52bfe8')]:
            shoulder = advance(base, torso, (sign*.63,1.0,0))
            frame = joint(arm, shoulder, torso, 'x', -1)
            box(shoulder,frame,(.25,.26,.36),color)
            roll = advance(shoulder,frame,(sign*.13,0,0))
            frame = joint(arm+1,roll,frame,'z',sign)
            # All arm servo values at zero correspond to a straight T pose.
            # This mounting offset changes only the model, not sent angles.
            frame = matmul(frame, rotation('z', sign * 90))
            box(advance(roll,frame,(0,-.30,0)),frame,(.25,.60,.28),color)
            elbow = advance(roll,frame,(0,-.62,0))
            frame = joint(arm+2,elbow,frame,'x',-1)
            box(elbow,frame,(.29,.19,.30),'#64748b')
            box(advance(elbow,frame,(0,-.29,0)),frame,(.29,.48,.32),color)
            box(advance(elbow,frame,(0,-.58,.03)),frame,(.32,.18,.38),'#dae2ed')
        self._scene_key = key
        self._scene_cache = (faces, joints)
        return self._scene_cache

    def camera(self, point):
        key = (self.pitch, self.yaw)
        if key != self._camera_key:
            self._camera_frame = matmul(rotation('x', self.pitch), rotation('y', self.yaw))
            self._camera_key = key
        x,y,z = point[0],point[1]-.25,point[2]
        return tuple(row[0]*x + row[1]*y + row[2]*z for row in self._camera_frame)

    def project(self, point):
        x,y,z = self.camera(point)
        scale = min(self.width()/4.8,self.height()/3.9) * 6 / (6-z)
        return QPointF(self.width()/2+x*scale,self.height()/2-y*scale)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor('#17212e'))
        painter.setPen(QPen(QColor('#304154'),1))
        for n in range(-4,5):
            v=n*.4
            painter.drawLine(self.project((v,-.77,-1.6)),self.project((v,-.77,1.6)))
            painter.drawLine(self.project((-1.6,-.77,v)),self.project((1.6,-.77,v)))
        faces,joints = self.scene()
        # Painter's algorithm: rear surfaces first, near surfaces last.
        for vertices,color in sorted(faces,key=lambda f: sum(self.camera(v)[2] for v in f[0])/4):
            painter.setBrush(color)
            painter.setPen(QPen(color, .6))
            painter.drawPolygon(QPolygonF([self.project(v) for v in vertices]))
        self.hits=[]
        for i,point,frame,axis in joints:
            screen=self.project(point)
            self.hits.append((i,screen))
            painter.setBrush(QColor('#ffed82' if i==self.active else '#17212e'))
            painter.setPen(QPen(QColor('#ffed82' if i==self.active else '#ffffff'),2))
            painter.drawEllipse(screen,6,6)
            if i==self.active:
                vector={'x':(.35,0,0),'y':(0,.35,0),'z':(0,0,.35)}[axis]
                painter.drawLine(self.project(advance(point,frame,tuple(-v for v in vector))),
                                 self.project(advance(point,frame,vector)))
                painter.drawText(screen+QPointF(10,-12),f'ID{i}')
        painter.setPen(QColor('#f3a35a'))
        painter.drawText(16,25,'● 右腕 / ROBOT RIGHT')
        painter.setPen(QColor('#52bfe8'))
        painter.drawText(16,47,'● 左腕 / ROBOT LEFT')
        painter.setPen(QColor('#d1d9e6'))
        painter.drawText(16,self.height()-15,'関節: 上下ドラッグ  |  空白: 視点回転  |  黄色の線: 選択関節の回転軸')
        origin=(1.25,-.75,0)
        for delta,label,color in [((.45,0,0),'左','#52bfe8'),((0,.45,0),'上','#8ad4ac'),((0,0,.65),'前','#f3a35a')]:
            end=tuple(origin[i]+delta[i] for i in range(3))
            painter.setPen(QPen(QColor(color),2))
            painter.drawLine(self.project(origin),self.project(end))
            painter.drawText(self.project(end)+QPointF(4,0),label)

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        nearby = [(math.hypot(p.x() - event.x(), p.y() - event.y()), i) for i, p in self.hits]
        distance, servo_id = min(nearby, default=(999, 0))
        self.drag_joint = servo_id if distance < 18 else None
        if self.drag_joint is not None:
            self.active = servo_id
            self.selected.emit(servo_id)
        self.drag_origin = event.pos()
        self.update()

    def mouseMoveEvent(self, event):
        if self.drag_origin is None:
            return
        delta = event.pos() - self.drag_origin
        if self.drag_joint is not None:
            control = self.controls[self.drag_joint]
            lo, hi = control.min_angle.value(), control.max_angle.value()
            if lo <= hi:
                control.angle.setValue(max(lo, min(hi, control.angle.value() - delta.y() * .5)))
        else:
            self.yaw += delta.x() * .5
            self.pitch = max(-85, min(85, self.pitch + delta.y() * .5))
        self.drag_origin = event.pos()
        self.update()

    def mouseReleaseEvent(self, event):
        self.drag_origin = None


class PoseGUI(RobiGUI):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Robi 上半身 姿勢エディター')
        # Remove lower-body controls from both the UI and every bulk operation.
        for control in self.controls:
            if control.id < 12:
                control.setParent(None)
                control.deleteLater()
        self.controls = [c for c in self.controls if c.id >= 12]
        self.all_on_button.setText('上半身 TORQUE ON')
        self.stop_button.setText('緊急: 全身 TORQUE OFF')
        self.resize(1100, 1000)
        self.pending = deque()
        self.ready = False
        self.rx = bytearray()
        self.view = PoseView(self.controls)
        self.layout().insertWidget(2, QLabel(
            '上半身（腰・首・両腕）のみ送信。形状は概略／角度の正負・ゼロ位置は実機未校正。\n'
            '編集だけでは送信されません。接続 → 上半身 TORQUE ON → 上半身の姿勢を送信。'))
        self.layout().insertWidget(3, self.view, 2)
        row = QHBoxLayout()
        self.selection = QLabel()
        row.addWidget(self.selection)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(-1500, 1500)
        row.addWidget(self.slider, 1)
        self.zero_all_button = QPushButton('全部0°（編集）')
        self.zero_all_button.setToolTip('上半身の全角度を0°にします。実機へは姿勢送信ボタンで反映します。')
        self.zero_all_button.clicked.connect(self.zero_all_angles)
        row.addWidget(self.zero_all_button)
        self.pose_button = QPushButton('上半身の姿勢を送信')
        row.addWidget(self.pose_button)
        self.layout().insertLayout(4, row)
        self.view.selected.connect(self.select_joint)
        self.slider.valueChanged.connect(self.change_angle)
        for control in self.controls:
            control.angle.valueChanged.connect(self.update_preview)
        self.pose_button.clicked.connect(self.send_pose)
        tools = QHBoxLayout()
        self.joint_picker = QComboBox()
        for i,name in SERVOS:
            if i >= 12:
                self.joint_picker.addItem(f'ID{i} {name}',i)
        tools.addWidget(self.joint_picker)
        self.joint_picker.currentIndexChanged.connect(
            lambda: self.select_joint(self.joint_picker.currentData()))
        for label,yaw,pitch in [('正面',0,0),('斜め',30,12),('側面',90,0),('背面',180,0)]:
            button=QPushButton(label)
            button.clicked.connect(lambda checked=False,y=yaw,p=pitch: self.set_camera(y,p))
            tools.addWidget(button)
        self.layout().insertLayout(4,tools)
        calibration=QHBoxLayout()
        calibration.addWidget(QLabel('選択関節の表示補正（送信角度は変更しません）'))
        self.reverse_box=QCheckBox('向きを反転')
        calibration.addWidget(self.reverse_box)
        calibration.addWidget(QLabel('モデルの0°に対応するサーボ角度'))
        self.zero_spin=QDoubleSpinBox()
        self.zero_spin.setRange(-150,150)
        calibration.addWidget(self.zero_spin)
        self.layout().insertLayout(6,calibration)
        self.reverse_box.toggled.connect(self.calibrate_view)
        self.zero_spin.valueChanged.connect(self.calibrate_view)
        self.select_joint(16)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.serial_tick)
        self.timer.start(60)

    def set_camera(self, yaw, pitch):
        self.view.yaw,self.view.pitch=yaw,pitch
        self.view.update()

    def calibrate_view(self, *args):
        i=self.view.active
        self.view.reverse[i]=self.reverse_box.isChecked()
        self.view.zero[i]=self.zero_spin.value()
        self.view.update()

    def select_joint(self, servo_id):
        self.view.active = servo_id
        for widget in (self.joint_picker,self.reverse_box,self.zero_spin):
            widget.blockSignals(True)
        self.joint_picker.setCurrentIndex(self.joint_picker.findData(servo_id))
        self.reverse_box.setChecked(self.view.reverse[servo_id])
        self.zero_spin.setValue(self.view.zero[servo_id])
        for widget in (self.joint_picker,self.reverse_box,self.zero_spin):
            widget.blockSignals(False)
        self.selection.setText(f'ID{servo_id} {dict(SERVOS)[servo_id]}')
        self.update_preview()

    def update_preview(self, *args):
        self.slider.blockSignals(True)
        self.slider.setValue(round(self.view.controls[self.view.active].angle.value() * 10))
        self.slider.blockSignals(False)
        self.view.update()

    def change_angle(self, value):
        control = self.view.controls[self.view.active]
        lo, hi = control.min_angle.value(), control.max_angle.value()
        if lo <= hi:
            control.angle.setValue(max(lo, min(hi, value / 10)))
        self.update_preview()

    def zero_all_angles(self):
        for control in self.controls:
            control.angle.blockSignals(True)
            control.angle.setValue(0.0)
            control.angle.blockSignals(False)
        self.update_preview()

    def send_pose(self):
        if any(c.min_angle.value() > c.max_angle.value() for c in self.controls):
            self.log.append('Min は Max 以下にしてください。')
            return
        if not self.ready:
            self.log.append('NOT CONNECTED / 接続準備中')
            return
        for control in self.controls:
            control.move()

    def connect_port(self):
        if self.ser is not None:
            self.disconnect_port()
            return
        port = self.ports.currentText()
        if not port:
            self.log.append('ポートを選択してください。')
            return
        try:
            self.ser = serial.Serial(port, 115200, timeout=0, write_timeout=.1)
            self.connect_button.setText('Disconnect')
            self.log.append(f'接続準備中 {port}')
            connection = self.ser
            QTimer.singleShot(2000, lambda: self.finish_connection(connection))
        except (serial.SerialException, OSError) as exc:
            self.log.append(str(exc))
            self.disconnect_port()

    def finish_connection(self, connection):
        if self.ser is connection:
            self.ready = True
            self.log.append('CONNECTED')

    def disconnect_port(self):
        self.ready = False
        self.pending.clear()
        self.rx.clear()
        if self.ser is not None:
            self.ser.close()
            self.ser = None
        self.connect_button.setText('Connect')

    def send(self, command):
        if command == 'STOP':
            self.pending.clear()
        if not self.ready:
            self.log.append('NOT CONNECTED / 接続準備中')
            return
        self.pending.append(command)
        if command == 'STOP':
            self.serial_tick()

    def serial_tick(self):
        if self.ser is None:
            return
        try:
            if self.ready and self.pending:
                command = self.pending.popleft()
                data = (command + '\n').encode()
                if self.ser.write(data) != len(data):
                    raise serial.SerialException('コマンドを完全に送信できませんでした。')
                self.log.append('> ' + command)
            self.rx.extend(self.ser.read(min(self.ser.in_waiting, 4096)))
            while b'\n' in self.rx:
                line, _, rest = self.rx.partition(b'\n')
                self.rx = bytearray(rest)
                self.log.append('< ' + line.decode(errors='replace').strip())
            if len(self.rx) > 8192:
                self.rx.clear()
        except (serial.SerialException, OSError) as exc:
            self.log.append(str(exc))
            self.disconnect_port()

    def closeEvent(self, event):
        self.timer.stop()
        self.disconnect_port()
        event.accept()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = PoseGUI()
    window.show()
    sys.exit(app.exec_())
