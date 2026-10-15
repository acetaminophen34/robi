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


class RobiGUI(QWidget):

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


if __name__ == "__main__":

    app = QApplication(
        sys.argv
    )

    gui = RobiGUI()

    gui.show()

    sys.exit(
        app.exec_()
    )
