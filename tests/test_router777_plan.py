import json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from router777_plan import plan
class Router777PlanTest(unittest.TestCase):
 def test_eight_bytecode_calls(self):
  for c in json.loads(Path('tests/fixtures/router777_plan.json').read_text()):self.assertEqual(plan(c['calldata']),c['expected'])
 def test_malformed_modes_rejected(self):
  raw=bytearray.fromhex(json.loads(Path('tests/fixtures/router777_plan.json').read_text())[0]['calldata'][2:])
  for word in [0,3,6,9,10,11,12]:
   changed=raw.copy();start=4+word*32;changed[start:start+32]=(99).to_bytes(32,'big')
   with self.assertRaises(ValueError):plan('0x'+changed.hex())
  with self.assertRaises(ValueError):plan('0x'+raw[:-1].hex())
if __name__=='__main__':unittest.main()
