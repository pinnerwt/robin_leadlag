import copy,json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from packed_routers import decode_packed
from v3_calldata import word
class UniversalPermitTest(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.f=json.loads(Path('tests/fixtures/universal_permit.json').read_text())
  cls.registry=json.loads(Path('config/optimistic-router-template.json').read_text())
 def decode(self,raw,pools=None,registry=None):
  return decode_packed(self.f['tx']['to'],raw,registry or self.registry,tracked_pools=self.f['pools'] if pools is None else pools)
 def test_verified_fixture(self):self.assertEqual(self.decode(self.f['tx']['data']),self.f['expected'])
 def test_unrecorded_pool(self):self.assertEqual(self.decode(self.f['tx']['data'],pools={}),[])
 def test_other_commands_and_truncation_rejected(self):
  raw=bytearray.fromhex(self.f['tx']['data'][2:]);start=4+word(raw[4:],0)+32
  for command in (0x8a,0x10,0):
   changed=raw.copy();changed[start]=command
   with self.assertRaises(ValueError):self.decode(changed)
  with self.assertRaises(ValueError):self.decode(raw[:-64])
 def test_code_pin_required(self):
  r=copy.deepcopy(self.registry);r['routers'][self.f['tx']['to'].lower()].pop('code_hash')
  with self.assertRaises(ValueError):self.decode(self.f['tx']['data'],registry=r)
if __name__=='__main__':unittest.main()
