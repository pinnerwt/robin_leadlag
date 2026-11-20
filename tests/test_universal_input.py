import json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from packed_routers import decode_packed
from v3_calldata import word,array
class UniversalInputTest(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.f=json.loads(Path('tests/fixtures/universal_input.json').read_text())
  cls.registry=json.loads(Path('config/optimistic-router-template.json').read_text())
 def decode(self,raw,pools=None):
  return decode_packed(self.f['tx']['to'],raw,self.registry,tracked_pools=self.f['pools'] if pools is None else pools)
 def test_bytecode_fixture_and_partial_status(self):
  self.assertEqual(self.decode(self.f['tx']['data']),self.f['expected'])
  self.assertIn('settlement',self.f['expected'][0]['coverage_note'])
 def test_dynamic_amount_and_extra_callback_rejected(self):
  raw=bytearray.fromhex(self.f['tx']['data'][2:]);d=raw[4:];body=array(d,word(d,1))[0];start=raw.find(body)
  for index,value in [(1,1<<255),(4,0),(9,1)]:
   changed=raw.copy();changed[start+index*32:start+(index+1)*32]=value.to_bytes(32,'big')
   with self.assertRaises(ValueError):self.decode(changed)
 def test_unrecorded_pool(self):self.assertEqual(self.decode(self.f['tx']['data'],{}),[])
if __name__=='__main__':unittest.main()
