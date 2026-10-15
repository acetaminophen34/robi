"""Standalone tabbed controller. Requires PyQt5 and pyserial; flash robi_esp.ino."""
import sys
import time
import serial
import serial.tools.list_ports
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QPushButton,
    QComboBox,
    QDoubleSpinBox,
    QSpinBox,
    QTextEdit,
    QScrollArea,
    QGroupBox,
)
import math
from collections import deque
from PyQt5.QtCore import QPointF, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QColor, QPainter, QPen, QPolygonF
from PyQt5.QtWidgets import QApplication, QHBoxLayout, QLabel, QPushButton, QSlider, QWidget, QComboBox, QCheckBox, QDoubleSpinBox
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QComboBox, QSpinBox, QSlider, QGroupBox,
    QCheckBox, QPlainTextEdit,
)
from PyQt5.QtWidgets import QSplitter, QLayout
from PyQt5.QtCore import QObject, QTimer, pyqtSignal
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTabWidget, QPlainTextEdit, QScrollArea, QCheckBox

SERVOS = [
    (2,  "右股関節 横回転"),
    (3,  "右股関節 縦回転"),
    (4,  "右ひざ"),
    (5,  "右足首 縦回転"),
    (6,  "右足首 横回転"),

    (7,  "左股関節 横回転"),
    (8,  "左股関節 縦回転"),
    (9,  "左ひざ"),
    (10, "左足首 縦回転"),
    (11, "左足首 横回転"),

    (12, "腰"),

    (13, "首 旋回"),
    (14, "首 横回転"),
    (15, "首 縦回転"),

    (16, "右肩"),
    (17, "右上腕"),
    (18, "右前腕"),

    (19, "左肩"),
    (20, "左上腕"),
    (21, "左前腕"),
]

class ServoControl(QGroupBox):

    def __init__(
        self,
        gui,
        servo_id,
        name
    ):
        super().__init__(
            f"ID{servo_id}  {name}"
        )

        self.gui = gui
        self.id = servo_id

        layout = QGridLayout()
        self.setLayout(layout)


        # ==========================================
        # Angle
        # ==========================================
        self.angle = QDoubleSpinBox()

        self.angle.setRange(
            -150.0,
            150.0
        )

        self.angle.setDecimals(1)
        self.angle.setSingleStep(1.0)

        self.angle.setValue(0.0)


        # ==========================================
        # GUI側Limit
        # ==========================================
        self.min_angle = QDoubleSpinBox()

        self.min_angle.setRange(
            -150.0,
            150.0
        )

        self.min_angle.setValue(
            -150.0
        )


        self.max_angle = QDoubleSpinBox()

        self.max_angle.setRange(
            -150.0,
            150.0
        )

        self.max_angle.setValue(
            150.0
        )


        # ==========================================
        # Buttons
        # ==========================================
        self.move_button = QPushButton(
            "MOVE"
        )

        self.center_button = QPushButton(
            "0°"
        )

        self.on_button = QPushButton(
            "Torque ON"
        )

        self.off_button = QPushButton(
            "Torque OFF"
        )


        # ==========================================
        # Layout
        # ==========================================
        layout.addWidget(
            QLabel("Angle"),
            0,
            0
        )

        layout.addWidget(
            self.angle,
            0,
            1
        )

        layout.addWidget(
            QLabel("Min"),
            1,
            0
        )

        layout.addWidget(
            self.min_angle,
            1,
            1
        )

        layout.addWidget(
            QLabel("Max"),
            1,
            2
        )

        layout.addWidget(
            self.max_angle,
            1,
            3
        )

        layout.addWidget(
            self.move_button,
            0,
            2
        )

        layout.addWidget(
            self.center_button,
            0,
            3
        )

        layout.addWidget(
            self.on_button,
            2,
            0,
            1,
            2
        )

        layout.addWidget(
            self.off_button,
            2,
            2,
            1,
            2
        )


        # ==========================================
        # Signals
        # ==========================================
        self.move_button.clicked.connect(
            self.move
        )

        self.center_button.clicked.connect(
            self.center
        )

        self.on_button.clicked.connect(
            self.torque_on
        )

        self.off_button.clicked.connect(
            self.torque_off
        )


    def move(self):

        degree = self.angle.value()

        minimum = self.min_angle.value()

        maximum = self.max_angle.value()

        degree = max(
            minimum,
            min(
                maximum,
                degree
            )
        )

        self.angle.setValue(
            degree
        )

        seconds = self.gui.move_time.value()

        self.gui.send(
            f"MOVE,"
            f"{self.id},"
            f"{degree:.1f},"
            f"{seconds:.2f}"
        )


    def center(self):

        self.angle.setValue(
            0.0
        )

        self.move()


    def torque_on(self):

        percent = self.gui.torque_percent.value()

        self.gui.send(
            f"PREPARE,"
            f"{self.id},"
            f"{percent}"
        )


    def torque_off(self):

        self.gui.send(
            f"TORQUE,"
            f"{self.id},0"
        )

class ServoPanel(QWidget):

    def __init__(self):
        super().__init__()

        self.ser = None

        self.setWindowTitle(
            "Robi Full Servo Controller"
        )

        self.resize(
            900,
            900
        )

        main = QVBoxLayout()
        self.setLayout(main)


        # ==========================================
        # Serial
        # ==========================================
        row = QHBoxLayout()

        self.ports = QComboBox()

        self.refresh_button = QPushButton(
            "Refresh"
        )

        self.connect_button = QPushButton(
            "Connect"
        )

        row.addWidget(
            self.ports
        )

        row.addWidget(
            self.refresh_button
        )

        row.addWidget(
            self.connect_button
        )

        main.addLayout(
            row
        )


        # ==========================================
        # Common
        # ==========================================
        common = QHBoxLayout()

        common.addWidget(
            QLabel("Move time")
        )

        self.move_time = QDoubleSpinBox()

        self.move_time.setRange(
            0.05,
            10.0
        )

        self.move_time.setValue(
            1.0
        )

        common.addWidget(
            self.move_time
        )


        common.addWidget(
            QLabel("Torque %")
        )

        self.torque_percent = QSpinBox()

        self.torque_percent.setRange(
            1,
            100
        )

        self.torque_percent.setValue(
            50
        )

        common.addWidget(
            self.torque_percent
        )


        self.all_on_button = QPushButton(
            "ALL TORQUE ON"
        )

        common.addWidget(
            self.all_on_button
        )

        self.stop_button = QPushButton(
            "ALL TORQUE OFF"
        )

        common.addWidget(
            self.stop_button
        )

        main.addLayout(
            common
        )


        # ==========================================
        # Scroll
        # ==========================================
        scroll = QScrollArea()

        scroll.setWidgetResizable(
            True
        )

        container = QWidget()

        servo_layout = QVBoxLayout(
            container
        )


        self.controls = []

        for servo_id, name in SERVOS:

            control = ServoControl(
                self,
                servo_id,
                name
            )

            self.controls.append(
                control
            )

            servo_layout.addWidget(
                control
            )


        servo_layout.addStretch()

        scroll.setWidget(
            container
        )

        main.addWidget(
            scroll
        )


        # ==========================================
        # Log
        # ==========================================
        self.log = QTextEdit()

        self.log.setReadOnly(
            True
        )

        self.log.setMaximumHeight(
            160
        )

        main.addWidget(
            self.log
        )


        # ==========================================
        # Signals
        # ==========================================
        self.refresh_button.clicked.connect(
            self.refresh_ports
        )

        self.connect_button.clicked.connect(
            self.connect_port
        )

        self.all_on_button.clicked.connect(
            self.all_torque_on
        )

        self.stop_button.clicked.connect(
            lambda:
            self.send("STOP")
        )

        self.refresh_ports()


    def all_torque_on(self):

        for control in self.controls:
            control.torque_on()


    def refresh_ports(self):

        self.ports.clear()

        for p in (
            serial.tools
            .list_ports
            .comports()
        ):
            self.ports.addItem(
                p.device
            )


    def connect_port(self):

        port = self.ports.currentText()

        if not port:
            return

        try:

            self.ser = serial.Serial(
                port,
                115200,
                timeout=0.1
            )

            time.sleep(
                2
            )

            self.ser.reset_input_buffer()

            self.log.append(
                f"CONNECTED {port}"
            )

        except Exception as e:

            self.log.append(
                str(e)
            )


    def send(
        self,
        command
    ):

        if self.ser is None:

            self.log.append(
                "NOT CONNECTED"
            )

            return

        self.ser.write(
            (
                command + "\n"
            ).encode()
        )

        self.ser.flush()

        self.log.append(
            "> " + command
        )

        # 簡単に応答を読む
        time.sleep(
            0.05
        )

        while (
            self.ser.in_waiting
            > 0
        ):

            line = (
                self.ser.readline()
                .decode(
                    errors="ignore"
                )
                .strip()
            )

            if line:

                self.log.append(
                    "< " + line
                )

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
        for servo_id in (12, 14, 17):
            self.reverse[servo_id] = True
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

class PoseGUI(ServoPanel):
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

class LEDGUI(QWidget):
    def __init__(self):
        super().__init__()
        self.ser = None
        self.ready = False
        self.rx = bytearray()
        self.handshake_at = 0
        self.deadline = 0
        self.setWindowTitle('Robi 目・口 LED コントローラー')
        self.resize(720, 540)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel('ESP32には robi_esp.ino を書き込んでください。'))
        row = QHBoxLayout()
        self.ports = QComboBox()
        row.addWidget(self.ports, 1)
        refresh = QPushButton('ポート更新')
        refresh.clicked.connect(self.refresh_ports)
        row.addWidget(refresh)
        self.connect_button = QPushButton('接続')
        self.connect_button.clicked.connect(self.connect_port)
        row.addWidget(self.connect_button)
        layout.addLayout(row)
        self.status = QLabel('未接続 / プレビューのみ')
        layout.addWidget(self.status)
        self.values = []
        self.swatches = []
        eyes = QHBoxLayout()
        for name in ('左目（基板 PWM0–2）', '右目（基板 PWM3–5）'):
            group = QGroupBox(name)
            grid = QGridLayout(group)
            swatch = QLabel('RGB 0, 0, 0')
            swatch.setAlignment(Qt.AlignCenter)
            swatch.setMinimumHeight(85)
            self.swatches.append(swatch)
            grid.addWidget(swatch, 0, 0, 1, 3)
            for index, channel in enumerate(('R', 'G', 'B'), 1):
                grid.addWidget(QLabel(channel), index, 0)
                slider = QSlider(Qt.Horizontal)
                slider.setRange(0, 255)
                spin = QSpinBox()
                spin.setRange(0, 255)
                slider.valueChanged.connect(spin.setValue)
                spin.valueChanged.connect(slider.setValue)
                spin.valueChanged.connect(self.changed)
                self.values.append(spin)
                grid.addWidget(slider, index, 1)
                grid.addWidget(spin, index, 2)
            eyes.addWidget(group)
        layout.addLayout(eyes)
        mouth_group = QGroupBox('口 LED（基板 PWM6）')
        mouth_layout = QHBoxLayout(mouth_group)
        self.mouth_preview = QLabel('消灯')
        self.mouth_preview.setAlignment(Qt.AlignCenter)
        self.mouth_preview.setMinimumSize(140, 36)
        mouth_layout.addWidget(self.mouth_preview)
        mouth_layout.addWidget(QLabel('明るさ'))
        self.mouth_slider = QSlider(Qt.Horizontal)
        self.mouth_slider.setRange(0, 255)
        mouth_layout.addWidget(self.mouth_slider, 1)
        mouth = QSpinBox()
        mouth.setRange(0, 255)
        self.mouth_slider.valueChanged.connect(mouth.setValue)
        mouth.valueChanged.connect(self.mouth_slider.setValue)
        mouth.valueChanged.connect(self.changed)
        self.values.append(mouth)
        mouth_layout.addWidget(mouth)
        for label, value in [('消灯', 0), ('50%', 128), ('最大', 255)]:
            button = QPushButton(label)
            button.clicked.connect(lambda checked=False, level=value: mouth.setValue(level))
            mouth_layout.addWidget(button)
        layout.addWidget(mouth_group)
        row = QHBoxLayout()
        self.live = QCheckBox('変更を自動送信')
        self.live.toggled.connect(self.live_changed)
        row.addWidget(self.live)
        self.send_button = QPushButton('LEDに反映')
        self.send_button.clicked.connect(self.send_values)
        row.addWidget(self.send_button)
        off = QPushButton('全消灯')
        off.clicked.connect(self.all_off)
        row.addWidget(off)
        layout.addLayout(row)
        presets = QHBoxLayout()
        presets.addWidget(QLabel('両目プリセット'))
        for name, rgb in [('白',(255,255,255)),('赤',(255,0,0)),('緑',(0,255,0)),
                          ('青',(0,0,255)),('水色',(0,180,255)),('紫',(180,0,255))]:
            button = QPushButton(name)
            button.clicked.connect(lambda checked=False, color=rgb: self.preset(color))
            presets.addWidget(button)
        layout.addLayout(presets)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(300)
        layout.addWidget(self.log)
        self.debounce = QTimer(self)
        self.debounce.setSingleShot(True)
        self.debounce.setInterval(100)
        self.debounce.timeout.connect(self.send_values)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll)
        self.timer.start(30)
        self.refresh_ports()
        self.changed()

    def refresh_ports(self):
        selected = self.ports.currentText()
        self.ports.clear()
        self.ports.addItems([p.device for p in serial.tools.list_ports.comports()])
        index = self.ports.findText(selected)
        if index >= 0:
            self.ports.setCurrentIndex(index)

    def changed(self, *args):
        for i, swatch in enumerate(self.swatches):
            r,g,b = [v.value() for v in self.values[i*3:i*3+3]]
            text = '#111' if .299*r+.587*g+.114*b > 140 else '#fff'
            swatch.setText(f'RGB {r}, {g}, {b}')
            swatch.setStyleSheet(f'background: rgb({r},{g},{b}); color:{text}; border-radius:18px;')
        brightness = self.values[6].value()
        self.mouth_preview.setText(f'{brightness / 255:.0%}' if brightness else '消灯')
        text = '#111' if brightness > 140 else '#fff'
        self.mouth_preview.setStyleSheet(
            f'background: rgb({brightness},{brightness},{brightness}); '
            f'color:{text}; border-radius:8px;')
        if self.live.isChecked() and self.ready:
            self.debounce.start()

    def live_changed(self, enabled):
        if not enabled:
            self.debounce.stop()
        else:
            self.changed()

    def preset(self, color):
        for widget, value in zip(self.values[:6], color * 2):
            widget.setValue(value)
        self.changed()

    def send_values(self):
        self.debounce.stop()
        self.send('LED,' + ','.join(str(v.value()) for v in self.values))

    def all_off(self):
        for widget in self.values:
            widget.setValue(0)
        self.debounce.stop()
        self.send('OFF')

    def connect_port(self):
        if self.ser is not None:
            self.disconnect()
            return
        port = self.ports.currentText()
        if not port:
            self.log.appendPlainText('ポートを選択してください。')
            return
        try:
            self.ser = serial.Serial(port, 115200, timeout=0, write_timeout=.1)
            self.connect_button.setText('切断')
            self.status.setText('LEDスケッチを確認中…')
            self.handshake_at = time.monotonic() + 2
            self.deadline = time.monotonic() + 6
        except (serial.SerialException, OSError) as exc:
            self.fail(exc)

    def send(self, command):
        if not self.ready:
            self.log.appendPlainText('未接続 / LEDスケッチを確認してください。')
            return
        try:
            self.write(command)
        except (serial.SerialException, OSError) as exc:
            self.fail(exc)

    def write(self, command):
        data = (command + '\n').encode('ascii')
        if self.ser.write(data) != len(data):
            raise serial.SerialException('送信が完了しませんでした。')
        self.log.appendPlainText('> ' + command)

    def poll(self):
        if self.ser is None:
            return
        try:
            now = time.monotonic()
            if not self.ready and now >= self.handshake_at:
                self.write('PING')
                self.handshake_at = now + 1
            self.rx.extend(self.ser.read(min(self.ser.in_waiting, 4096)))
            while b'\n' in self.rx:
                line, _, rest = self.rx.partition(b'\n')
                self.rx = bytearray(rest)
                text = line.decode(errors='replace').strip()
                self.log.appendPlainText('< ' + text)
                if text == 'ROBI_LED_V1':
                    self.ready = True
                    self.status.setText('接続済み / LEDコントローラー')
                elif text.startswith('ERR'):
                    self.status.setText(text)
            if len(self.rx) > 8192:
                raise serial.SerialException('受信データが長すぎます。')
            if not self.ready and now >= self.deadline:
                raise serial.SerialException('LEDスケッチの応答がありません。LED_gui.ino を確認してください。')
        except (serial.SerialException, OSError) as exc:
            self.fail(exc)

    def fail(self, exc):
        self.log.appendPlainText(str(exc))
        self.disconnect()

    def disconnect(self):
        self.ready = False
        self.debounce.stop()
        self.rx.clear()
        if self.ser is not None:
            self.ser.close()
            self.ser = None
        self.connect_button.setText('接続')
        self.status.setText('未接続 / プレビューのみ')

    def closeEvent(self, event):
        self.timer.stop()
        self.disconnect()
        event.accept()

class Connection(QObject):
    message = pyqtSignal(str)
    connected = pyqtSignal(bool)
    received = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.ser = None
        self.ready = False
        self.queue = deque()
        self.rx = bytearray()
        self.waiting = None
        self.deadline = 0
        self.ping_at = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(20)

    def open(self, port):
        if not port:
            self.message.emit('ポートを選択してください。')
            return
        try:
            self.ser = serial.Serial(port, 115200, timeout=0, write_timeout=.1)
            self.ping_at = time.monotonic() + 2
            self.deadline = time.monotonic() + 7
            self.message.emit('統合スケッチを確認中…')
        except (serial.SerialException, OSError) as exc:
            self.fail(exc)

    def close(self):
        port, self.ser = self.ser, None
        self.ready = False
        self.queue.clear()
        self.rx.clear()
        self.waiting = None
        if port is not None:
            try:
                port.close()
            except (serial.SerialException, OSError) as exc:
                self.message.emit(str(exc))
        self.connected.emit(False)

    def fail(self, exc):
        self.message.emit(str(exc))
        self.close()

    def send(self, command):
        if not self.ready:
            self.message.emit('未接続 / robi_esp.ino を確認してください。')
            return
        if command == 'STOP':
            self.queue.clear()
            self.waiting = None
            try:
                self.dispatch(command)
            except (serial.SerialException, OSError) as exc:
                self.fail(exc)
            return
        if command == 'OFF' or command.startswith('LED,'):
            # Keep the most recent LED edit, without delaying servo commands.
            self.queue = deque(c for c in self.queue if not c.startswith('LED,') and c != 'OFF')
        if command == 'OFF':
            self.queue.appendleft(command)
        else:
            if command.startswith('STATUS,'):
                if command not in self.queue:
                    self.queue.append(command)
            else:
                # User actions take priority over queued read-only polling.
                index = next((i for i,c in enumerate(self.queue) if c.startswith('STATUS,')), len(self.queue))
                self.queue.insert(index, command)

    def write(self, command):
        data = (command + '\n').encode('ascii')
        if self.ser.write(data) != len(data):
            raise serial.SerialException('送信が完了しませんでした。')
        self.message.emit('> ' + command)

    def dispatch(self, command):
        self.write(command)
        verb = command.split(',')[0]
        self.waiting = 'OK,' + ('LED' if verb == 'OFF' else verb)
        self.deadline = time.monotonic() + 3

    def tick(self):
        if self.ser is None:
            return
        try:
            now = time.monotonic()
            if not self.ready and now >= self.ping_at:
                self.write('PING')
                self.ping_at = now + 1
            self.rx.extend(self.ser.read(min(self.ser.in_waiting, 4096)))
            while b'\n' in self.rx:
                line, _, rest = self.rx.partition(b'\n')
                self.rx = bytearray(rest)
                text = line.decode(errors='replace').strip()
                self.message.emit('< ' + text)
                self.received.emit(text)
                if text == 'ROBI_COMBINED_V2' and not self.ready:
                    self.ready = True
                    self.connected.emit(True)
                elif self.waiting and (text == self.waiting or text.startswith(self.waiting + ',')):
                    self.waiting = None
                elif text.startswith('ERR,'):
                    self.waiting = None
                    self.queue.clear()
            if len(self.rx) > 8192:
                raise serial.SerialException('受信行が長すぎます。')
            if (not self.ready or self.waiting) and now >= self.deadline:
                raise serial.SerialException('応答タイムアウト。接続と統合スケッチを確認してください。')
            if self.ready and not self.waiting and self.queue:
                self.dispatch(self.queue.popleft())
        except (serial.SerialException, OSError) as exc:
            self.fail(exc)

def hide_row(layout):
    for i in range(layout.count()):
        item = layout.itemAt(i)
        if item.widget() is not None:
            item.widget().hide()

class RobiGUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Robi ポーズ・LED コントローラー')
        screen = QApplication.primaryScreen().availableGeometry()
        self.resize(min(1000, screen.width()-40), min(740, screen.height()-60))
        layout = QVBoxLayout(self)
        self.pose = PoseGUI()
        self.led = LEDGUI()
        self.pose.timer.stop()
        self.led.timer.stop()
        self.connection = Connection(self)
        # Reuse the existing controls, with a single owner for the serial port.
        pose_serial_row = self.pose.layout().takeAt(0).layout()
        self.pose.connect_button.clicked.disconnect()
        self.pose.connect_button.clicked.connect(self.toggle_connection)
        layout.addLayout(pose_serial_row)
        self.status = QLabel('未接続 — ESP32に robi_esp/robi_esp.ino を書き込んでください。')
        layout.addWidget(self.status)
        emergency_row = QHBoxLayout()
        emergency = QPushButton('緊急: 全身 TORQUE OFF')
        emergency.clicked.connect(self.stop)
        emergency_row.addWidget(emergency)
        off = QPushButton('目・口 全消灯')
        off.clicked.connect(self.led.all_off)
        emergency_row.addWidget(off)
        layout.addLayout(emergency_row)
        self.led.layout().itemAt(0).widget().hide()
        hide_row(self.led.layout().itemAt(1).layout())
        self.led.status.hide()
        self.pose.log.hide()
        self.led.log.hide()
        self.led.layout().addStretch(1)
        self.tabs = QTabWidget()
        self.pose_page = QWidget()
        page_layout = QVBoxLayout(self.pose_page)
        page_layout.setContentsMargins(4,4,4,4)
        page_layout.setSpacing(3)
        actions = QHBoxLayout()
        for label, widget in [('移動秒', self.pose.move_time), ('トルク%', self.pose.torque_percent)]:
            actions.addWidget(QLabel(label))
            actions.addWidget(widget)
        actions.addWidget(self.pose.all_on_button)
        actions.addWidget(self.pose.zero_all_button)
        self.pose.pose_button.setText('姿勢を送信')
        actions.addWidget(self.pose.pose_button)
        page_layout.addLayout(actions)
        self.splitter = QSplitter(Qt.Horizontal)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0,0,0,0)
        left_layout.setSpacing(3)
        self.pose.view.setMinimumSize(280,220)
        left_layout.addWidget(self.pose.view,1)
        cameras = QHBoxLayout()
        for title,yaw,pitch in [('正面',0,0),('斜め',30,12),('側面',90,0),('背面',180,0)]:
            button = QPushButton(title)
            button.clicked.connect(lambda checked=False,y=yaw,p=pitch: self.pose.set_camera(y,p))
            cameras.addWidget(button)
        left_layout.addLayout(cameras)
        left_layout.addWidget(self.pose.joint_picker)
        calibration = QHBoxLayout()
        calibration.addWidget(self.pose.reverse_box)
        calibration.addWidget(QLabel('表示の0°補正'))
        calibration.addWidget(self.pose.zero_spin)
        left_layout.addLayout(calibration)
        note = QLabel('現在角度の取得時にモデル・指定角度も更新します。自動更新中は編集値も上書きされます。')
        note.setWordWrap(True)
        left_layout.addWidget(note)
        self.axis_panel = QWidget()
        self.axis_layout = QVBoxLayout(self.axis_panel)
        self.axis_layout.setContentsMargins(4,0,0,0)
        self.axis_layout.setSpacing(3)
        self.axis_grid = QGridLayout()
        self.axis_grid.setVerticalSpacing(2)
        self.axis_layout.addLayout(self.axis_grid)
        self.axis_layout.addStretch()
        self.splitter.addWidget(left)
        self.splitter.addWidget(self.axis_panel)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setSizes([500,400])
        page_layout.addWidget(self.splitter,1)
        self.pose.hide()
        self.tabs.addTab(self.pose_page, 'ポーズ（上半身）')
        for child_layout in self.led.findChildren(QLayout):
            child_layout.setSpacing(3)
            child_layout.setContentsMargins(4,4,4,4)
        for swatch in self.led.swatches:
            swatch.setMinimumHeight(55)
        self.tabs.addTab(self.led, '目・口 LED')
        layout.addWidget(self.tabs, 1)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(400)
        self.log.setMaximumHeight(80)
        self.log.setMinimumHeight(40)
        show_log = QCheckBox('通信ログを表示')
        show_log.toggled.connect(self.log.setVisible)
        layout.addWidget(show_log)
        self.log.hide()
        layout.addWidget(self.log)
        self.connection.message.connect(self.log.appendPlainText)
        self.connection.connected.connect(self.connection_changed)
        self.pose.send = self.send
        self.led.send = self.send
        # Route validation messages from the reused pages to the shared log too.
        self.pose.log.textChanged.connect(self.copy_pose_log)
        self.samples = {}
        self.actual_labels = {}
        for col, title in enumerate(('軸', '指定角度 °', '現在角度 °')):
            self.axis_grid.addWidget(QLabel(title),0,col)
        for row, control in enumerate(self.pose.controls,1):
            name = QPushButton(f'{control.id} {dict(SERVOS)[control.id]}')
            name.setFlat(True)
            name.clicked.connect(lambda checked=False,i=control.id: self.pose.select_joint(i))
            self.axis_grid.addWidget(name,row,0)
            control.angle.setMinimumWidth(80)
            self.axis_grid.addWidget(control.angle,row,1)
            label = QLabel('未取得')
            label.setMinimumWidth(125)
            self.axis_grid.addWidget(label,row,2)
            self.actual_labels[control.id] = label
        read_row = QHBoxLayout()
        read_button = QPushButton('全軸の現在角度を取得')
        read_button.clicked.connect(self.read_positions)
        read_row.addWidget(read_button)
        self.auto_read = QCheckBox('自動更新')
        read_row.addWidget(self.auto_read)
        self.current_position = QLabel('選択関節の現在角度: 未取得')
        self.current_position.setWordWrap(True)
        self.axis_layout.insertLayout(0, read_row)
        self.axis_layout.addWidget(self.current_position)
        self.read_index = 0
        self.read_timer = QTimer(self)
        self.read_timer.setInterval(200)
        self.read_timer.timeout.connect(self.poll_positions)
        self.read_timer.start()
        self.connection.received.connect(self.receive_position)
        self.pose.joint_picker.currentIndexChanged.connect(self.refresh_positions)
        self.connection_changed(False)

    def read_positions(self):
        if not self.connection.ready:
            self.log.appendPlainText('現在角度の取得には接続が必要です。')
            self.current_position.setText('現在角度: 未接続')
            return
        for control in self.pose.controls:
            self.connection.send(f'STATUS,{control.id}')

    def poll_positions(self):
        self.refresh_positions()
        if (self.auto_read.isChecked() and self.connection.ready
                and not self.connection.waiting and not self.connection.queue):
            control = self.pose.controls[self.read_index]
            self.connection.send(f'STATUS,{control.id}')
            self.read_index = (self.read_index + 1) % len(self.pose.controls)

    def receive_position(self, text):
        fields = text.split(',')
        if len(fields) != 3 or fields[0] != 'STATUS':
            return
        try:
            servo_id = int(fields[1])
            value = None if fields[2] == 'NA' else float(fields[2])
            if servo_id not in self.actual_labels or (value is not None and not math.isfinite(value)):
                return
        except ValueError:
            return
        self.samples[servo_id] = (value, time.monotonic())
        if value is not None:
            # Angle edits update the preview only; movement requires explicit send.
            self.pose.view.controls[servo_id].angle.setValue(value)
        self.refresh_positions()

    def refresh_positions(self, *args):
        for servo_id, label in self.actual_labels.items():
            sample = self.samples.get(servo_id)
            if sample is None:
                text = '未取得'
            elif sample[0] is None:
                text = '応答なし'
            else:
                age = time.monotonic() - sample[1]
                text = f'{sample[0]:.1f}° / {age:.0f}秒前' + ('（古い値）' if age > 5 else '')
            label.setText(text)
            label.setToolTip('取得できない場合は通信ログの STATUS_RX を確認してください。')
            if servo_id == self.pose.view.active:
                self.current_position.setText(f'ID{servo_id} 現在角度: ' + text)

    def copy_pose_log(self):
        text = self.pose.log.toPlainText()
        if text:
            self.log.appendPlainText(text)
            self.pose.log.clear()

    def send(self, command):
        if command == 'STOP':
            self.led.debounce.stop()
        self.connection.send(command)

    def stop(self):
        self.send('STOP')

    def toggle_connection(self):
        if self.connection.ser is not None:
            self.connection.close()
        else:
            self.connection.open(self.pose.ports.currentText())
            if self.connection.ser is not None:
                self.pose.connect_button.setText('切断')
                self.status.setText('統合スケッチを確認中…')

    def connection_changed(self, ready):
        self.pose.ready = self.led.ready = ready
        self.pose.connect_button.setText('切断' if ready else '接続')
        self.status.setText('接続済み / ポーズ・LED 共通接続' if ready else '未接続 / robi_esp.ino を使用してください。')
        if not ready:
            self.led.debounce.stop()
            self.samples.clear()
            self.refresh_positions()

    def closeEvent(self, event):
        self.read_timer.stop()
        self.led.debounce.stop()
        self.connection.timer.stop()
        self.connection.close()
        event.accept()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = RobiGUI()
    window.show()
    sys.exit(app.exec_())
