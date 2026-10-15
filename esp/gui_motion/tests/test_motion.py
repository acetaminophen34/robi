import copy
import json
import unittest
from pathlib import Path
from motion_lib.motion import extract, validate, check_limits

HEART=Path(__file__).resolve().parents[3]/'Robi-heart'

class ConversionTests(unittest.TestCase):
    def test_real_motion_json_roundtrip(self):
        data=extract(HEART/'握手右.RM4',HEART/'STARTUP.XML')
        self.assertEqual(len(data['frames']),9)
        self.assertEqual(validate(json.loads(json.dumps(data))),data)
        self.assertEqual(data['frames'][0]['angles']['2'],0.6)
        self.assertEqual(data['frames'][0]['duration_ms'],333)

    def test_invalid_json(self):
        data=extract(HEART/'握手右.RM4',HEART/'STARTUP.XML')
        for field,value in [('duration_ms',float('nan')),('duration_ms',-1)]:
            bad=copy.deepcopy(data); bad['frames'][0][field]=value
            with self.assertRaises(ValueError): validate(bad)
        bad=copy.deepcopy(data); bad['frames'][0]['angles']['2']=999
        with self.assertRaises(ValueError): check_limits(bad)
        del bad['frames'][0]['angles']['3']
        with self.assertRaises(ValueError): validate(bad)

    def test_torque_rows_and_unknown_actions(self):
        from motion_lib.motion import check_transport
        action={'type':'torque','name':'OFF','enabled':False,'duration_ms':0}
        data={'format':'robi-motion-v1','frames':[action]}
        validate(data); check_limits(data); check_transport(data)
        for field,value in [('enabled',0),('duration_ms',True),('duration_ms',50),
                            ('type','unknown'),('angles',{})]:
            bad=copy.deepcopy(data); bad['frames'][0][field]=value
            with self.assertRaises(ValueError): validate(bad)

if __name__=='__main__': unittest.main()
