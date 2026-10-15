"""Local PC audio playback; loaded only for sequences containing audio."""
from pathlib import Path
from PyQt5.QtCore import QObject, QTimer, QUrl, pyqtSignal


class AudioPlayer(QObject):
    finished=pyqtSignal()
    failed=pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.player=None
        self.active=False
        self.start_timer=QTimer(self)
        self.start_timer.setSingleShot(True)
        self.start_timer.timeout.connect(self.start_timeout)

    def start(self, path):
        from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent
        self.stop()
        if not Path(path).is_file(): raise ValueError(f'音声ファイルが見つかりません: {path}')
        player=QMediaPlayer(self)
        if not player.isAvailable():
            player.deleteLater()
            raise ValueError('PCの音声再生機能を利用できません（QtMultimedia）')
        self.player=player; self.active=True
        def status(value):
            if self.player is not player: return
            if value==QMediaPlayer.EndOfMedia:
                self.stop(); self.finished.emit()
            elif value==QMediaPlayer.InvalidMedia:
                self.fail(player.errorString() or '音声ファイルを再生できません')
        def error(value):
            if self.player is player and value!=QMediaPlayer.NoError:
                self.fail(player.errorString() or '音声の再生に失敗しました')
        def position(value):
            if self.player is player and value>0: self.start_timer.stop()
        player.mediaStatusChanged.connect(status)
        player.error.connect(error)
        player.positionChanged.connect(position)
        self.start_timer.start(10000)
        player.setMedia(QMediaContent(QUrl.fromLocalFile(str(Path(path).resolve()))))
        if self.player is player: player.play()

    def start_timeout(self):
        if self.active: self.fail('音声の再生開始がタイムアウトしました')

    def fail(self, message):
        self.stop(); self.failed.emit(message)

    def stop(self):
        self.start_timer.stop()
        player=self.player; self.player=None; self.active=False
        if player is not None:
            player.stop(); player.deleteLater()
