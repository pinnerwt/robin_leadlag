import json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from universal_v4_intent import inspect
from v3_calldata import word,array
class V4IntentTest(unittest.TestCase):
 def test_nine_bytecode_calls(self):
  cases=json.loads(Path('tests/fixtures/universal_v4_intent.json').read_text())
  for c in cases:self.assertEqual(inspect(bytes.fromhex(c['payload'])),c['expected'])
 def test_unknown_hook_data_rejected(self):
  c=json.loads(Path('tests/fixtures/universal_v4_intent.json').read_text())[0]
  raw=bytearray.fromhex(c['payload']);b=array(raw,word(raw,1))[0];start=raw.find(b)
  for field,value in [(6,2),(7,1<<128),(9,1),(11,1)]:
   changed=raw.copy();changed[start+field*32:start+(field+1)*32]=value.to_bytes(32,'big')
   with self.assertRaises(ValueError):inspect(changed)
if __name__=='__main__':unittest.main()
