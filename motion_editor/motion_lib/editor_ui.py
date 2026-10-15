"""Tabbed controls for the motion editor; playback stays in robi_gui.py."""
from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import QIcon, QPainter, QPen, QPixmap
from PyQt5.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QHBoxLayout,
                            QLabel, QLineEdit, QPlainTextEdit, QPushButton, QSpinBox,
                            QStyle, QTableWidget, QTabWidget, QToolButton,
                            QVBoxLayout, QWidget)


def button(window, text, callback, tip, icon=None):
    control=QPushButton(text)
    control.setToolTip(tip); control.setAccessibleName(text)
    if icon is not None: control.setIcon(window.style().standardIcon(icon))
    control.clicked.connect(callback)
    return control


def icon_button(window, name, callback, tip, icon):
    control=QToolButton()
    control.setIcon(icon if isinstance(icon,QIcon) else window.style().standardIcon(icon))
    control.setIconSize(QSize(20,20)); control.setFixedSize(34,32)
    control.setToolTip(tip); control.setAccessibleName(name)
    control.clicked.connect(callback)
    return control


def copy_icon(window):
    pixmap=QPixmap(24,24); pixmap.fill(Qt.transparent)
    painter=QPainter(pixmap); painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(QPen(window.palette().text().color(),1.6))
    painter.drawRoundedRect(8,3,12,14,2,2)
    painter.setBrush(window.palette().window()); painter.drawRoundedRect(3,8,12,14,2,2)
    painter.end()
    return QIcon(pixmap)


def build(window):
    layout=QVBoxLayout(window); layout.setSpacing(8)
    header=QHBoxLayout(); layout.addLayout(header)
    title=QLabel('Robi モーションエディタ'); title.setStyleSheet('font-size: 17px; font-weight: 600;')
    header.addWidget(title)
    window.status_label=QLabel('未接続'); window.status_label.setStyleSheet('color: #667085; margin-left: 10px;')
    header.addWidget(window.status_label); header.addStretch()
    window.play_button=button(window,'選択行を再生',window.play,
        '選択した行を上から順に実機で再生します。PC音声も再生します。',QStyle.SP_MediaPlay)
    header.addWidget(button(window,'モーションプレーヤー',window.open_player,
        'フォルダのモーションを一覧から選び、詳細表示・全体再生・編集できます。'))
    header.addWidget(window.play_button)
    window.stop_button=button(window,'停止・トルクOFF',window.stop,
        '実機再生・待機・PC音声を停止し、全軸のトルクをOFFにします。',QStyle.SP_MediaStop)
    window.stop_button.setStyleSheet('QPushButton { color: #b42318; font-weight: 600; padding: 6px 12px; }')
    header.addWidget(window.stop_button)

    line=QHBoxLayout(); layout.addLayout(line)
    line.addWidget(QLabel('モーション名')); window.motion_name=QLineEdit(); line.addWidget(window.motion_name)
    line.addWidget(QLabel('動作説明')); window.motion_description=QLineEdit(); line.addWidget(window.motion_description,2)
    line=QHBoxLayout(); layout.addLayout(line)
    for side, label in [('start','開始'),('end','終了')]:
        line.addWidget(QLabel(label+'状態'))
        combo=QComboBox(); combo.setMinimumWidth(110); setattr(window, side+'_state',combo); line.addWidget(combo)
        line.addWidget(button(window,label+'状態を反映',lambda checked=False,s=side:window.apply_state(s),
                              '選択状態を先頭／末尾に反映します。再反映は既存の反映行を置換します。'))
    line.addWidget(QLabel('移動時間')); window.state_time=QSpinBox()
    window.state_time.setRange(50,163830); window.state_time.setValue(1000); window.state_time.setSuffix(' ms')
    line.addWidget(window.state_time)
    line.addWidget(button(window,'共通状態を管理',window.manage_states,'別ウィンドウで共通状態を登録・編集します。'))

    window.tabs=QTabWidget(); layout.addWidget(window.tabs)
    window.tabs.setToolTip('操作の種類ごとに切り替えます。下のモーション表は共通です。')
    def tab(name):
        page=QWidget(); box=QVBoxLayout(page); box.setSpacing(8)
        window.tabs.addTab(page,name)
        return box
    def row(box):
        result=QHBoxLayout(); box.addLayout(result); return result

    record=tab('姿勢・動作の記録')
    line=row(record); line.addWidget(QLabel('姿勢名'))
    window.pose_name=QLineEdit('記録した姿勢'); line.addWidget(window.pose_name,1)
    window.pose_name.setToolTip('取得する姿勢の名前。記録後も表で変更できます。')
    line.addWidget(QLabel('移動時間'))
    window.pose_time=QSpinBox(); window.pose_time.setRange(50,163830); window.pose_time.setValue(1000)
    window.pose_time.setSuffix(' ms'); window.pose_time.setToolTip('この姿勢へ移動する時間です。')
    line.addWidget(window.pose_time)
    line.addWidget(button(window,'現在角度を記録',window.capture_pose,
        '実機の20軸の現在角度を読み取り、末尾に姿勢を追加します。移動やトルク切替は行いません。',QStyle.SP_DialogSaveButton))
    line=row(record); line.addWidget(QLabel('待機時間'))
    window.delay_time=QSpinBox(); window.delay_time.setRange(1,2147483647); window.delay_time.setValue(1000)
    window.delay_time.setSuffix(' ms'); window.delay_time.setToolTip('トルク・位置の指令を変えずに待つ時間です。')
    line.addWidget(window.delay_time)
    line.addWidget(button(window,'待機を追加',window.record_delay,
        '選択行の直後（未選択なら末尾）に、指定時間だけ待つ行を追加します。',QStyle.SP_MediaPause))
    line.addStretch()
    for text,enabled in [('トルクOFFを追加',False),('トルクONを追加',True)]:
        line.addWidget(button(window,text,lambda checked=False,value=enabled:window.record_torque(value),
            '選択行の直後（未選択なら末尾）にトルク切替の行を追加します。実行は再生時です。'))
    record.addWidget(QLabel('待機・トルク切替は選択行の直後へ追加。現在角度の記録は末尾へ追加。'))

    audio=tab('PC音声')
    line=row(audio); line.addWidget(QLabel('音声ファイル'))
    window.audio_path=QLineEdit(); window.audio_path.setPlaceholderText('PC上の音声ファイルのパス')
    window.audio_path.setToolTip('PCのスピーカーから再生する音声ファイルのパス。直接入力もできます。')
    line.addWidget(window.audio_path,1)
    line.addWidget(button(window,'参照…',window.choose_audio,'PC上の音声ファイルを選びます。',QStyle.SP_DirOpenIcon))
    line=row(audio); window.audio_wait=QCheckBox('音声終了まで待つ')
    window.audio_wait.setToolTip('ON: 音声終了後に次の行へ進みます。OFF: 次の動作と並行して再生します。')
    line.addWidget(window.audio_wait); line.addStretch()
    line.addWidget(button(window,'音声再生を追加',window.record_audio,
        '選択行の直後（未選択なら末尾）に音声の再生開始を追加します。追加時には再生しません。',QStyle.SP_MediaVolume))
    audio.addWidget(QLabel('PCのスピーカーから再生。ファイルのパスと終了待ちは表でも変更できます。'))

    files=tab('取り込み・保存')
    line=row(files)
    for text,callback,tip in [
        ('JSONを取り込む',window.open_json,'保存したモーションJSONを取り込みます。'),
        ('RM4を取り込む',window.open_rm4,'ジャンプをたどり、条件経路を選んでRM4の実行順を取り込みます。'),
        ('RM4の全姿勢を抽出',window.open_raw_rm4,'RM4内の姿勢をファイル記載順で抽出します。実行順とは異なります。')]:
        line.addWidget(button(window,text,callback,tip,QStyle.SP_DialogOpenButton))
    line.addStretch()
    line=row(files); window.append_import=QCheckBox('取り込み時に末尾へ追加'); window.append_import.setChecked(True)
    window.append_import.setToolTip('ON: 編集中の表の末尾へ追加。OFF: 最後の選択行の直後に挿入します。未選択なら末尾へ追加します。')
    line.addWidget(window.append_import); line.addStretch()
    line.addWidget(button(window,'選択行を保存',window.save,'選択した行だけをJSONに保存します。',QStyle.SP_DialogSaveButton))
    line.addWidget(button(window,'全体を保存',window.save_all,'表の全行をJSONに保存します。',QStyle.SP_DialogSaveButton))
    files.addWidget(QLabel('チェックONは末尾へ追加、OFFは選択行の直後へ挿入。未選択なら末尾へ追加。'))

    hardware=tab('接続・実機')
    line=row(hardware); line.addWidget(QLabel('ポート'))
    window.port=QComboBox(); window.port.setMinimumWidth(240); line.addWidget(window.port,1)
    window.port.setToolTip('ESP32が接続されているシリアルポートを選びます。')
    line.addWidget(icon_button(window,'ポート更新',window.ports,'使用可能なシリアルポートを更新します。',QStyle.SP_BrowserReload))
    line.addWidget(button(window,'接続／切断',window.connect,'選択したポートへ接続します。接続済みなら停止して切断します。'))
    line.addWidget(button(window,'トルクON',lambda:window.send('TORQUE,1'),
        '実機の全軸のトルクを今すぐONにします。記録行の追加ではありません。'))
    window.ignore_limits=QCheckBox('暫定の角度リミットを無視して送信'); window.ignore_limits.setChecked(True)
    window.ignore_limits.setToolTip('ON: 暫定可動範囲を無視。OFF: 暫定範囲も検証します。通信の範囲は常に検証します。')
    hardware.addWidget(window.ignore_limits)
    hardware.addWidget(QLabel('接続だけでは動きません。再生・停止は画面右上から操作できます。'))

    preview=tab('3Dプレビュー')
    line=row(preview)
    line.addWidget(button(window,'3Dを開く',window.open_preview,'実機へ送信しない3Dプレビュー画面を開きます。'))
    line.addWidget(button(window,'選択行を3Dで再生',window.play_preview,'選択行を3Dモデルで再生します。PC音声は再生しません。',QStyle.SP_MediaPlay))
    line.addWidget(button(window,'軸推定の詳細',window.show_axis_report,'Heartの姿勢から推定した表示用の軸符号と根拠を表示します。',QStyle.SP_MessageBoxInformation))
    line.addStretch()
    preview.addWidget(QLabel('関節・寸法は未校正の概略表示です。脱力後の姿勢変化や音声再生は再現しません。'))
    preview.addStretch()

    tools=QHBoxLayout(); layout.addLayout(tools); tools.addWidget(QLabel('モーション'))
    for name,callback,tip,icon in [
        ('新規',window.new_motion,'表を空にして新規モーションを作成します。必要な内容は先に保存してください。',QStyle.SP_FileIcon),
        ('全行選択',lambda:window.table.selectAll(),'表の全行を選択します。',QStyle.SP_DialogApplyButton),
        ('複製',window.duplicate_rows,'選択行を複製し、それぞれの直後に追加します。',copy_icon(window)),
        ('削除',window.delete_rows,'選択行を表から削除します。',QStyle.SP_TrashIcon),
        ('上へ',lambda:window.move_rows(-1),'選択行を1行上へ移動します。',QStyle.SP_ArrowUp),
        ('下へ',lambda:window.move_rows(1),'選択行を1行下へ移動します。',QStyle.SP_ArrowDown)]:
        tools.addWidget(icon_button(window,name,callback,tip,icon))
    tools.addStretch(); tools.addWidget(QLabel('上から順に再生 · セルで編集'))
    window.table=QTableWidget(0,25)
    window.table.setHorizontalHeaderLabels(['姿勢名','時間ms']+[f'ID{i} °' for i in range(2,22)]+['動作','音声ファイル','音声終了待ち'])
    window.table.setSelectionBehavior(QAbstractItemView.SelectRows)
    window.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
    window.table.horizontalHeader().moveSection(22,0)
    layout.addWidget(window.table,1)

    window.log_toggle=QToolButton(); window.log_toggle.setText('通信ログ'); window.log_toggle.setCheckable(True)
    window.log_toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon); window.log_toggle.setArrowType(Qt.RightArrow)
    window.log_toggle.setToolTip('通信応答・再生状況・エラーのログを開閉します。')
    layout.addWidget(window.log_toggle)
    window.log=QPlainTextEdit(); window.log.setReadOnly(True); window.log.setMaximumHeight(90)
    window.log.hide(); layout.addWidget(window.log)
    def toggle_log(checked):
        window.log.setVisible(checked)
        window.log_toggle.setArrowType(Qt.DownArrow if checked else Qt.RightArrow)
    window.log_toggle.toggled.connect(toggle_log)
    def show_errors():
        last=window.log.document().lastBlock().text()
        if last.startswith(('ERR,','応答タイムアウト','停止応答なし','古いino')):
            window.log_toggle.setChecked(True)
    window.log.textChanged.connect(show_errors)


def refresh_status(window):
    if window.playing:
        state={'DELAY':'待機中','AUDIO':'音声終了待ち','AUDIO_END':'音声終了待ち'}.get(window.pending,'再生中')
    elif window.pending=='READ_ALL': state='角度を取得中'
    elif window.pending=='STOP': state='停止確認中'
    elif window.ready: state='接続済み'
    elif window.link: state='接続確認中'
    else: state='未接続'
    if window.status_label.text()!=state: window.status_label.setText(state)
