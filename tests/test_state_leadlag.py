import io
import json
import math
from pathlib import Path
import random
import struct
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from state_leadlag import hy_scan, increments, analyze
from tape import read, MAGIC

class ReplayTests(unittest.TestCase):
    def test_hy_sign_and_resolution(self):
        rng=random.Random(421);t=0;p=100;x=[]
        for _ in range(2000):
            t+=rng.randrange(30,150);p*=math.exp(rng.gauss(0,.001));x.append((t,p))
        y=[(t+150,p) for t,p in x]
        result=hy_scan(x,y,0,t,50,500)
        self.assertEqual(result['peak_ms'],150)
        self.assertGreater(result['peak_contrast'],result['zero_contrast'])
        shifted=hy_scan([(t+75,p) for t,p in x],[(t-175,p) for t,p in y],0,t,50,500)
        self.assertEqual(shifted['peak_ms'],-100)
    def test_same_arrival_uses_final_state(self):
        rows=increments([(0,100),(1,101),(1,102)],0,2,10)
        self.assertEqual(len(rows),1)
        self.assertAlmostEqual(rows[0][2],math.log(1.02))
        self.assertEqual(increments([(0,100),(1,None),(1,102)],0,2,10),[])
    def test_invalid_state_breaks_intervals(self):
        self.assertEqual(increments([(0,100),(1,None),(2,102)],0,2,10),[])
        report=analyze([dict(kind='bbo',symbol='X',mono_ns=1,bid='1',ask='2')])
        self.assertEqual(report['status'],'no_verified_state_quotes')
        with self.assertRaises(ValueError):analyze([],x_ms=100)
    def test_legacy_positional_binary_and_truncation(self):
        payload=bytes([10])+struct.pack('<H',1)+bytes([5])+struct.pack('<d',12.75)
        tape=MAGIC+struct.pack('<I',len(payload))+payload
        self.assertEqual(list(read(io.BytesIO(tape))),[dict(kind='bbo',ms=12.75)])
        with self.assertRaises(ValueError):list(read(io.BytesIO(tape[:-1])))
    def test_no_cross_session_clock_join(self):
        with self.assertRaises(ValueError):analyze([dict(kind='session'),dict(kind='session')])

if __name__=='__main__':unittest.main()
