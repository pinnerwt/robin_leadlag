import json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from packed_routers import decode_packed,inspect_29,ROUTER_520,ROUTER_C33
from v3_calldata import decode
ROOT=Path(__file__).resolve().parents[1]
class PackedRouterTests(unittest.TestCase):
 def setUp(self):self.registry=json.loads((ROOT/'config/packed-routers.json').read_text())
 def test_deployed_bytecode_fixtures(self):
  for f in json.loads((ROOT/'tests/fixtures/packed_router_calls.json').read_text()):
   op=decode_packed(f['router'],f['calldata'],self.registry)[0]
   self.assertEqual({k:op[k] for k in f['expected']},f['expected'])
   self.assertEqual(decode(f['router'],f['calldata'],{op['pool']:{}},set(),packed_registry=self.registry),[op])
 def test_missing_routes_and_truncation(self):
  for data in ('0xb2460c48','0xb2460c48'+('ff'*32)):
   with self.assertRaises(ValueError):decode_packed(ROUTER_520,data,self.registry)
  with self.assertRaises(ValueError):decode_packed(ROUTER_C33,'0x000000e7',self.registry)
 def test_intent_requires_dependencies(self):
  payload=(1).to_bytes(2,'big')+bytes([5])+(123).to_bytes(16,'big')+(456).to_bytes(20,'big')+(789).to_bytes(16,'big')
  op=inspect_29(bytes.fromhex('9c909e3f')+payload)[0]
  self.assertEqual((op['pool_index'],op['requested_amount'],op['limit'],op['unresolved_constraint']),(1,123,456,789))
  self.assertTrue(op['balance_cap']);self.assertFalse(op['executable'])
  self.assertNotIn('amount',op)
if __name__=='__main__':unittest.main()
