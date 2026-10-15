import copy
import json
import os
from pathlib import Path
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from robi_gui import QApplication, Window


class Link:
    def __init__(self):
        self.incoming=bytearray()
        self.sent=[]
    @property
    def in_waiting(self): return len(self.incoming)
    def read(self, n):
        data=bytes(self.incoming[:n]); del self.incoming[:n]; return data
    def write(self, data): self.sent.append(data)
    def close(self): pass
    def respond(self, text): self.incoming.extend(text.encode('ascii'))


class EditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.w=Window(); self.errors=[]; self.w.error=lambda e:self.errors.append(str(e))
        self.data=json.loads((Path(__file__).resolve().parents[1]/'examples/motion-v1.json').read_text())

    def tearDown(self): self.w.close()

    def test_import_keeps_cell_edits_and_reorders_metadata(self):
        self.w.load(self.data)
        self.w.table.item(0,0).setText('編集済み')
        incoming=copy.deepcopy(self.data); incoming['frames']=incoming['frames'][:1]
        incoming['frames'][0]['source_file']='import.RM4'
        self.w.import_data(incoming)
        self.assertEqual(self.w.all_data()['frames'][0]['name'],'編集済み')
        self.w.table.selectRow(4); self.w.move_rows(-1)
        self.assertEqual(self.w.all_data()['frames'][3]['source_file'],'import.RM4')
        self.w.duplicate_rows()
        self.assertEqual(len(self.w.all_data()['frames']),6)
        self.w.delete_rows()
        self.assertEqual(len(self.w.all_data()['frames']),5)
        self.assertFalse(self.errors)

    def test_capture_requires_complete_fresh_read_and_never_moves(self):
        link=Link(); self.w.link=link; self.w.ready=True; self.w.can_capture=True
        self.w.pose_name.setText('実測'); self.w.pose_time.setValue(700)
        self.w.capture_pose()
        link.respond(''.join(f'POSE,{i},{-i/10}\n' for i in range(2,22))+'DONE,READ_ALL\n')
        self.w.poll()
        frame=self.w.all_data()['frames'][0]
        self.assertEqual(frame['angles']['21'],-2.1)
        self.assertEqual(frame['name'],'実測')
        self.assertEqual(frame['duration_ms'],700)
        self.assertEqual(link.sent,[b'READ_ALL\n'])
        self.w.capture_pose()
        link.respond('POSE,2,99\nERR,READ,3\n'); self.w.poll()
        self.assertEqual(len(self.w.all_data()['frames']),1)
        self.w.capture_pose()
        link.respond('POSE,2,99\nDONE,READ_ALL\n'); self.w.poll()
        self.assertEqual(len(self.w.all_data()['frames']),1)
        self.assertTrue(self.errors)

    def test_stop_discards_late_capture_and_v2_cannot_capture(self):
        link=Link(); self.w.link=link; self.w.ready=True
        self.w.capture_pose()
        self.assertEqual(link.sent,[])
        self.w.can_capture=True; self.w.capture_pose(); self.w.stop()
        link.respond(''.join(f'POSE,{i},0\n' for i in range(2,22))+'DONE,READ_ALL\nOK,STOP\n')
        self.w.poll()
        self.assertIsNone(self.w.data)
        self.assertIsNone(self.w.pending)
        self.assertEqual(link.sent,[b'READ_ALL\n',b'STOP\n'])

    def test_torque_record_roundtrip_and_acknowledged_playback(self):
        self.w.load(self.data)
        self.w.table.selectRow(0); self.w.record_torque(False)
        self.w.record_torque(True)
        data=json.loads(json.dumps(self.w.all_data()))
        self.assertEqual([f.get('type','pose') for f in data['frames'][:4]],
                         ['pose','torque','torque','pose'])
        self.assertNotIn('angles',data['frames'][1])
        self.w.load(data); self.w.table.selectAll()
        link=Link(); self.w.link=link; self.w.ready=True
        self.w.play()
        self.assertTrue(link.sent[-1].startswith(b'FRAME_RAW,'))
        link.respond('OK,FRAME\n'); self.w.poll()
        self.assertEqual(len(link.sent),1)
        link.respond('DONE,FRAME\n'); self.w.poll()
        self.assertEqual(link.sent[-1],b'TORQUE,0\n')
        self.assertEqual(self.w.index,1)
        link.respond('OK,STOP\n'); self.w.poll()
        self.assertEqual(link.sent[-1],b'TORQUE,1\n')
        link.respond('OK,TORQUE\n'); self.w.poll()
        self.assertTrue(link.sent[-1].startswith(b'FRAME_RAW,'))
        self.assertEqual(self.w.index,3)
        self.assertFalse(self.errors)

    def test_off_at_end_completes_and_stop_cannot_advance(self):
        self.w.load({'format':'robi-motion-v1','frames':[self.data['frames'][0]]})
        self.w.record_torque(False); self.w.table.selectAll()
        link=Link(); self.w.link=link; self.w.ready=True
        self.w.play(); link.respond('DONE,FRAME\n'); self.w.poll()
        link.respond('OK,STOP\n'); self.w.poll()
        self.assertFalse(self.w.playing)
        self.assertEqual(len(link.sent),2)
        self.w.table.selectAll(); self.w.play()
        link.respond('DONE,FRAME\n'); self.w.poll(); self.w.stop()
        count=len(link.sent)
        link.respond('OK,STOP\nOK,STOP\n'); self.w.poll()
        self.assertEqual(len(link.sent),count)
        self.assertFalse(self.w.playing)

    def test_off_before_pose_is_rejected_before_any_send(self):
        self.w.load(self.data); self.w.table.selectRow(0); self.w.record_torque(False)
        self.w.table.selectAll()
        link=Link(); self.w.link=link; self.w.ready=True
        self.w.play()
        self.assertEqual(link.sent,[])
        self.assertIn('トルクON',self.errors[-1])


if __name__=='__main__': unittest.main()
