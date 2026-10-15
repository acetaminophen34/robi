import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import unittest
from PyQt5.QtCore import QCoreApplication, QEvent
from robi_gui import QApplication, Window, ROOT
from motion_lib.motion import extract

class PreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])

    def test_bilateral_rotations_are_mirrored(self):
        from motion_lib.preview import Preview, REFERENCE
        from motion_lib.axis_signs import PAIRS
        p=Preview()
        for right,left,_,_ in PAIRS:
            p.view.controls[right].angle.setValue(REFERENCE[right]+20)
            p.view.controls[left].angle.setValue(REFERENCE[left]-20)
        _, joints=p.view.scene()
        frames={i:frame for i,_,frame,_ in joints}
        reflect=[-1,1,1]
        for right,left,_,_ in PAIRS:
            for row in range(3):
                for col in range(3):
                    self.assertAlmostEqual(frames[left][row][col],
                                           reflect[row]*frames[right][row][col]*reflect[col])
        p.close()

    def test_offline_preview_releases_and_reopens(self):
        w=Window()
        self.assertIsNone(w.preview)
        w.load(extract(ROOT/'Robi-heart/握手右.RM4',ROOT/'Robi-heart/STARTUP.XML'))
        w.table.selectRow(0)
        w.play_preview()
        p=w.preview
        self.app.processEvents()
        self.assertTrue(p.timer.isActive())
        self.assertIsNone(w.link)
        self.assertIsNone(w.pending)
        p.pause()
        p.position=p.ends[-1]/2
        p.render()
        self.assertAlmostEqual(p.view.controls[2].angle.value(),(2.5+.6)/2)
        p.position=p.ends[-1]
        p.render()
        self.assertAlmostEqual(p.view.controls[2].angle.value(),.6)
        p.close()
        self.assertFalse(p.timer.isActive())
        QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
        self.app.processEvents()
        self.assertIsNone(w.preview)
        w.open_preview()
        self.assertIsNot(w.preview,p)
        w.close()

    def test_torque_events_keep_preview_pose_and_support_zero_length(self):
        from motion_lib.preview import Preview, REFERENCE
        p=Preview()
        off={'type':'torque','name':'OFF','enabled':False,'duration_ms':0}
        p.play({'format':'robi-motion-v1','frames':[off]})
        p.pause(); p.render()
        self.assertEqual(p.view.controls[13].angle.value(),REFERENCE[13])
        self.assertIn('トルクOFF',p.status.text())
        data=extract(ROOT/'Robi-heart/握手右.RM4',ROOT/'Robi-heart/STARTUP.XML')
        data['frames']=data['frames'][:1]+[off]
        p.play(data); p.pause(); p.position=p.ends[-1]; p.render()
        self.assertEqual(p.view.controls[13].angle.value(),data['frames'][0]['angles']['13'])
        self.assertIn('トルクOFF',p.status.text()); p.close()

if __name__=='__main__': unittest.main()
