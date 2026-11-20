import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from v4_delta import decode
class V4DeltaTest(unittest.TestCase):
 def test_signed_boundaries(self):
  for a in [-(1<<127),-1,0,1,(1<<127)-1]:
   for b in [-(1<<127),-1,0,1,(1<<127)-1]:
    raw=(((a% (1<<128))<<128)|(b%(1<<128))).to_bytes(32,'big')
    self.assertEqual(decode(raw),(a,b))
 def test_invalid_width(self):
  for n in [0,31,33,64]:
   with self.assertRaises(ValueError):decode(bytes(n))
if __name__=='__main__':unittest.main()
