import json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path('scripts').resolve()))
from router0480_v4_route import inspect,wrap

class V4RouteTest(unittest.TestCase):
 def cases(self):return json.loads(Path('reports/amm/router0480-wrap.json').read_text())['cases']
 def test_wrap_matches_actual_router_value_and_target(self):
  for row in self.cases():
   w=wrap(row['original_tx']['data'],row['command_offset'],row['command_stop']);c=row['result']['calls'][0]
   self.assertIsNone(row['result']['error']);self.assertEqual(w,dict(to=c['to'],data=c['data'],value=int(c['value'])))
 def test_original_routes_include_recorded_pool(self):
  for row in self.cases():
   p=inspect(row['original_tx']['data']);self.assertIn('0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca',p['pools']);self.assertEqual(p['wrap']['value'],p['swaps'][0]['amount']);self.assertFalse(p['execution_complete'])
 def test_corrupt_wrap_pointer_rejected(self):
  row=self.cases()[0];raw=bytearray.fromhex(row['original_tx']['data'][2:]);i=row['command_offset'];raw[i+1:i+3]=b'\xff\xff'
  with self.assertRaises(ValueError):inspect('0x'+raw.hex())
 def test_wrong_guard_pool_rejected(self):
  row=self.cases()[0];raw=bytearray.fromhex(row['original_tx']['data'][2:]);p=inspect(row['original_tx']['data']);i=p['guards'][1]['offset'];raw[i+4]^=1
  with self.assertRaises(ValueError):inspect('0x'+raw.hex())
