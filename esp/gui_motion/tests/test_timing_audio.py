import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PyQt5.QtCore import QObject, Qt, pyqtSignal

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from robi_gui import QApplication, Window
from motion_lib.motion import validate, check_sequence, check_limits, check_transport, resolve_audio_paths
from tests.test_editor import Link


class FakeAudio(QObject):
    finished=pyqtSignal()
    failed=pyqtSignal(str)
    def __init__(self):
        super().__init__(); self.active=False; self.paths=[]
    def start(self,path): self.paths.append(path); self.active=True
    def stop(self): self.active=False
    def finish(self): self.active=False; self.finished.emit()


class MediaBackend(QObject):
    EndOfMedia=7; InvalidMedia=8; NoError=0
    mediaStatusChanged=pyqtSignal(int)
    error=pyqtSignal(int)
    positionChanged=pyqtSignal(int)
    def isAvailable(self): return True
    def setMedia(self, media): self.media=media
    def play(self): pass
    def stop(self): pass
    def errorString(self): return 'decode failed'


class TimingAudioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name).resolve()
        self.path=self.root/'声 with spaces.wav'; self.path.write_bytes(b'placeholder')
        self.w=Window(); self.errors=[]; self.w.error=lambda e:self.errors.append(str(e))
        self.link=Link(); self.w.link=self.link; self.w.ready=True
        self.audio=FakeAudio(); self.w.audio=self.audio
        self.audio.finished.connect(self.w.audio_finished); self.audio.failed.connect(self.w.audio_failed)
        self.pose=json.loads((Path(__file__).resolve().parents[1]/'examples/motion-v1.json').read_text())['frames'][0]
    def tearDown(self): self.w.close(); self.temp.cleanup()
    def sound(self,wait=False):
        return {'type':'audio','name':'音声','path':str(self.path),'wait':wait,'duration_ms':0}
    def run_frames(self,frames):
        self.w.load({'format':'robi-motion-v1','frames':frames}); self.w.table.selectAll(); self.w.play()

    def test_delay_retains_off_state_and_sends_nothing_until_timer_finishes(self):
        self.run_frames([{'type':'torque','name':'OFF','enabled':False,'duration_ms':0},
                         {'type':'delay','name':'待機','duration_ms':1000},self.sound(True)])
        self.link.respond('OK,STOP\n'); self.w.poll()
        self.assertEqual(self.w.pending,'DELAY'); self.assertTrue(self.w.delay_timer.isActive())
        self.assertEqual(self.link.sent,[b'TORQUE,0\n'])
        with patch('robi_gui.time.monotonic',return_value=10**12): self.w.poll()
        self.assertEqual(self.w.pending,'DELAY')
        self.w.delay_timer.stop(); self.w.delay_finished()
        self.assertEqual(self.w.pending,'AUDIO'); self.assertEqual(self.audio.paths,[str(self.path)])
        self.audio.finish(); self.assertFalse(self.w.playing)
        self.assertEqual(self.link.sent,[b'TORQUE,0\n'])

    def test_async_audio_overlaps_pose_and_session_waits_for_tail(self):
        self.run_frames([self.sound(),self.pose])
        self.assertTrue(self.audio.active); self.assertEqual(self.w.pending,'FRAME')
        self.link.respond('DONE,FRAME\n'); self.w.poll()
        self.assertEqual(self.w.pending,'AUDIO_END'); self.assertTrue(self.w.playing)
        self.audio.finish(); self.assertFalse(self.w.playing); self.assertIsNone(self.w.pending)

    def test_wait_audio_defers_pose_and_stop_cancels_delay_and_audio(self):
        self.run_frames([self.sound(True),self.pose])
        self.assertEqual(self.link.sent,[])
        self.audio.finish(); self.assertTrue(self.link.sent[-1].startswith(b'FRAME_RAW,'))
        self.w.stop(); self.link.respond('OK,STOP\n'); self.w.poll()
        self.run_frames([self.sound(),{'type':'delay','name':'待機','duration_ms':1000},self.pose])
        self.w.stop(); count=len(self.link.sent)
        self.assertFalse(self.w.delay_timer.isActive()); self.assertFalse(self.audio.active)
        self.w.delay_finished(); self.audio.finish()
        self.assertEqual(len(self.link.sent),count)

    def test_missing_audio_preflight_and_runtime_failure_stop_motion(self):
        frame=self.sound(); frame['path']=str(self.root/'missing.wav')
        self.run_frames([self.pose,frame]); self.assertEqual(self.link.sent,[])
        self.run_frames([self.sound(),self.pose]); self.audio.failed.emit('decode error')
        self.assertFalse(self.w.playing); self.assertEqual(self.link.sent[-1],b'STOP\n')
        self.assertIn('decode error',self.errors)

    def test_import_paths_survive_merge_export_and_cell_edits(self):
        self.w.load({'format':'robi-motion-v1','frames':[self.pose]})
        frame=self.sound(); frame['path']=self.path.name
        self.w.import_data({'format':'robi-motion-v1','frames':[frame]},self.root)
        self.w.table.selectRow(1); self.w.delay_time.setValue(2500); self.w.record_delay()
        self.w.table.item(2,1).setText('3210')
        self.w.table.item(1,24).setCheckState(Qt.Checked)
        data=json.loads(json.dumps(self.w.all_data()))
        self.assertEqual(data['frames'][1]['path'],str(self.path))
        self.assertTrue(data['frames'][1]['wait'])
        self.assertEqual(data['frames'][2]['duration_ms'],3210)
        self.w.load(data); self.assertEqual(self.w.all_data(),data)

    def test_validation_and_preview_delay(self):
        delay={'type':'delay','name':'待機','duration_ms':1000}
        data={'format':'robi-motion-v1','frames':[delay,self.sound()]}
        validate(data); check_limits(data); check_transport(data); check_sequence(data)
        for bad_frame in [dict(delay,duration_ms=0),dict(delay,duration_ms=1.5),
                          dict(delay,duration_ms=True),dict(self.sound(),wait='yes'),
                          dict(self.sound(),duration_ms=1),dict(self.sound(),path='')]:
            with self.assertRaises(ValueError): validate(dict(data,frames=[bad_frame]))
        from motion_lib.preview import Preview
        p=Preview(); p.play({'format':'robi-motion-v1','frames':[self.pose,delay,self.sound()]})
        p.pause(); p.position=p.ends[0]+.5; p.render()
        self.assertEqual(p.view.controls[13].angle.value(),self.pose['angles']['13'])
        self.assertAlmostEqual(p.ends[-1],self.pose['duration_ms']/1000+1); p.close()

    def test_native_wrapper_timeout_completion_and_stale_callbacks(self):
        from motion_lib.audio import AudioPlayer
        from PyQt5 import QtMultimedia
        audio=AudioPlayer(); finished=[]; failed=[]
        audio.finished.connect(lambda:finished.append(True)); audio.failed.connect(failed.append)
        with patch.object(QtMultimedia,'QMediaPlayer',MediaBackend), patch.object(QtMultimedia,'QMediaContent',lambda url:url):
            audio.start(str(self.path)); old=audio.player
            self.assertTrue(audio.start_timer.isActive())
            old.positionChanged.emit(0); self.assertTrue(audio.start_timer.isActive())
            audio.start_timeout(); self.assertFalse(audio.active); self.assertEqual(len(failed),1)
            audio.start(str(self.path)); current=audio.player
            old.mediaStatusChanged.emit(MediaBackend.EndOfMedia)
            old.error.emit(1); self.assertTrue(audio.active); self.assertEqual(len(failed),1)
            current.positionChanged.emit(100); self.assertFalse(audio.start_timer.isActive())
            current.mediaStatusChanged.emit(MediaBackend.EndOfMedia)
            self.assertEqual(finished,[True]); self.assertFalse(audio.active)
            audio.start(str(self.path)); audio.player.error.emit(1)
            self.assertEqual(failed[-1],'decode failed'); self.assertFalse(audio.active)
            audio.stop(); audio.start_timeout(); self.assertEqual(len(failed),2)


if __name__=='__main__': unittest.main()
