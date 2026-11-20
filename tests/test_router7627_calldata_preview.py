import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path('scripts').resolve()))
from v3_state import State,Q96
from router7627_calldata_preview import decode,CODE_HASH,ROUTER
class CalldataPreviewTest(unittest.TestCase):
 def setUp(self):
  self.data='0x'+(20).to_bytes(4,'big').hex()+(15000).to_bytes(4,'big').hex()+'00'
  self.v3=State(Q96,0,1000,100,1,{},{});self.v4=State(Q96,0,1000,40,1,{},{})
 def test_noop_requires_no_tick_data(self):
  for timestamp,reason in ((21,'expired'),(20,'inside_price_band')):
   result=decode(ROUTER,self.data,timestamp,self.v3,self.v4,code_hash=CODE_HASH)
   self.assertEqual(result['status'],'no_swap');self.assertEqual(result['reason'],reason);self.assertEqual(result['swaps'],[]);self.assertFalse(result['state_applied'])
 def test_unsupported_profiles_not_silently_skipped(self):
  with self.assertRaisesRegex(ValueError,'code profile'):decode(ROUTER,self.data,20,self.v3,self.v4,code_hash='0x00')
  with self.assertRaisesRegex(ValueError,'entry profile'):decode(ROUTER,self.data+'00',20,self.v3,self.v4,code_hash=CODE_HASH)
  self.v4.sqrt=Q96*1001//1000
  with self.assertRaisesRegex(ValueError,'forward optimizer'):decode(ROUTER,self.data,20,self.v3,self.v4,code_hash=CODE_HASH)
