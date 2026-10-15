"""Run: python3 led_gui.py. Flash head/LED_gui/LED_gui.ino first."""
import sys
import time
import serial
import serial.tools.list_ports
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QComboBox, QSpinBox, QSlider, QGroupBox,
    QCheckBox, QPlainTextEdit,
)


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
        layout.addWidget(QLabel('ESP32には head/LED_gui/LED_gui.ino を書き込んでください。'))
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


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = LEDGUI()
    window.show()
    sys.exit(app.exec_())
