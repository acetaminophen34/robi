import tempfile
import unittest
from pathlib import Path
from motion_lib.route import resolve, RouteCancelled

HEART=Path(__file__).resolve().parents[3]/'Robi-heart'

class RouteTests(unittest.TestCase):
    def test_sitting_follows_cp932_byte_jumps(self):
        def unexpected(c): self.fail('座りの経路で不要な分岐が発生しました')
        data=resolve(HEART/'座り.RM4',HEART/'STARTUP.XML',unexpected,root=HEART)
        self.assertEqual([f['name'] for f in data['frames']],
                         ['POSE 8','POSE 2','POSE 1','POSE 3','POSE 4','POSE 0'])
        raw=(HEART/'座り.RM4').read_bytes()
        for f in data['frames']:
            self.assertTrue(raw[f['source_address']:].startswith(b'<mem_w'))

    def test_handshake_choice_and_cancel(self):
        data=resolve(HEART/'握手右.RM4',HEART/'STARTUP.XML',lambda c:'jump',root=HEART)
        self.assertEqual(data['frames'][0]['name'],'POSE 0')
        self.assertEqual(data['frames'][-1]['name'],'POSE 3')
        self.assertEqual(len(data['route_choices']),2)
        with self.assertRaises(RouteCancelled):
            resolve(HEART/'握手右.RM4',HEART/'STARTUP.XML',lambda c:None,root=HEART)

    def test_loop_is_bounded_and_invalid_target_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'loop.RM4'
            p.write_bytes(b'<jump adr="0x00000000"/>')
            with self.assertRaisesRegex(ValueError,'100回'):
                resolve(p,HEART/'STARTUP.XML',lambda c:'jump')
            p.write_bytes(b'<jump adr="0x00000001"/>')
            with self.assertRaisesRegex(ValueError,'ジャンプ先'):
                resolve(p,HEART/'STARTUP.XML',lambda c:'jump')

    def test_external_call_and_return(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            (root/'座り.RM4').write_bytes((HEART/'座り.RM4').read_bytes())
            p=root/'entry.RM4'
            p.write_bytes('<call filename="座り.RM4"/>\r\n<return/>'.encode('cp932'))
            data=resolve(p,HEART/'STARTUP.XML',lambda c:'jump',root=root)
            self.assertEqual(len(data['frames']),6)
            self.assertEqual(data['frames'][-1]['name'],'POSE 0')

if __name__=='__main__': unittest.main()
