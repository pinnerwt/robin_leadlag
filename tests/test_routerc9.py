import copy,json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from c9_router import C9
from packed_routers import decode_packed
class RouterC9Test(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.fixture=json.loads(Path('tests/fixtures/routerc9.json').read_text())
  cls.registry=json.loads(Path('config/optimistic-router-template.json').read_text())
 def decode(self,data,pools=None,registry=None):
  return decode_packed(C9,data,registry or self.registry,tracked_pools=self.fixture['pools'] if pools is None else pools)
 def test_real_prefix_fixtures(self):
  for row in self.fixture['cases']:
   self.assertEqual(self.decode(row['tx']['data']),row['expected'])
   self.assertIn('upstream',row['expected'][0]['coverage_note'])
 def test_multiple_callbacks_and_changed_amount_rejected(self):
  original=bytearray.fromhex(self.fixture['cases'][0]['tx']['data'][2:])
  for offset,value in [(4+31*32,2),(4+2*32,1),(4+4*32,0)]:
   raw=original.copy();raw[offset:offset+32]=value.to_bytes(32,'big')
   with self.assertRaises(ValueError):self.decode('0x'+raw.hex())
 def test_truncation_and_other_selector_rejected(self):
  data=self.fixture['cases'][0]['tx']['data']
  for raw in [data[:-2],'0xc7e280dd'+data[10:]]:
   with self.assertRaises(ValueError):self.decode(raw)
 def test_unrecorded_callback_does_not_hide_primary_uncertainty(self):
  with self.assertRaises(ValueError):self.decode(self.fixture['cases'][0]['tx']['data'],pools={})
 def test_requires_implementation_pin(self):
  r=copy.deepcopy(self.registry);del r['routers'][C9]['implementation_code_hash']
  with self.assertRaises(ValueError):self.decode(self.fixture['cases'][0]['tx']['data'],registry=r)
if __name__=='__main__':unittest.main()
