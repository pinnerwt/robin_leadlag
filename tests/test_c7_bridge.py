import copy,json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from c7_state_bridge import Bridge
from c9_balance_route import plan
from v3_state import State,sqrt_tick

class C7BridgeTest(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.case=json.loads(Path('tests/fixtures/c7_settlement.json').read_text())[0]
  cls.route=plan(cls.case['calldata'])
  cls.pool='0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca'
 def bridge(self,inventory=0):
  r=self.route
  pool=dict(pool=self.pool,tokens=[r['token_out'],r['token_in']],fee=100,spacing=1,
            sqrt=str(sqrt_tick(-201180)),tick=-201180,liquidity=str(10**20),
            bitmap={str(i):0 for i in range(-800,-770)},ticks={})
  seed=dict(complete=True,anchor=dict(hash='test'),pools=[pool])
  allocations=dict(anchor_hash='test',strategies=[dict(maker=r['maker'],program=r['program'],program_hash='0x'+'11'*32,
                    balances={r['token_in']:self.case['old_in'],r['token_out']:self.case['old_out']})],
                   router_inventory={r['token_out']:inventory})
  return Bridge(seed,allocations)
 def snapshot(self,b):return copy.deepcopy((b.states,b.allocations,b.inventory))
 def test_sequential_state_and_nonzero_inventory(self):
  b=self.bridge(12345)
  first=b.apply(self.case['calldata'])
  self.assertEqual(first['v3']['amount0'],first['aqua']['amount_out']+12345)
  self.assertEqual(first['router_output_inventory'],0)
  second=b.apply(self.case['calldata'])
  self.assertLess(second['aqua']['amount_out'],first['aqua']['amount_out'])
  self.assertNotEqual(second['v3']['sqrt'],first['v3']['sqrt'])
 def test_missing_v3_rolls_back_everything(self):
  b=self.bridge();b.states[self.pool].bitmap={};before=self.snapshot(b)
  with self.assertRaisesRegex(ValueError,'bitmap'):b.apply(self.case['calldata'])
  self.assertEqual(self.snapshot(b),before)
 def test_unrecorded_dependency_needs_state(self):
  b=self.bridge();b.meta={};before=self.snapshot(b)
  with self.assertRaisesRegex(ValueError,'callback pool state'):b.apply(self.case['calldata'])
  self.assertEqual(self.snapshot(b),before)
 def test_unknown_inventory_and_invalidated_state_rejected(self):
  b=self.bridge();b.inventory={};before=self.snapshot(b)
  with self.assertRaisesRegex(ValueError,'inventory'):b.apply(self.case['calldata'])
  self.assertEqual(self.snapshot(b),before)
  b.invalidate('unhandled transfer')
  with self.assertRaisesRegex(ValueError,'unhandled transfer'):b.apply(self.case['calldata'])
 def test_anchor_mismatch(self):
  with self.assertRaisesRegex(ValueError,'anchors differ'):
   Bridge(dict(anchor=dict(hash='a')),dict(anchor_hash='b'))
 def push(self,amount=7,app=None,strategy=None,token=None):
  from hub_state import AGGREGATOR
  r=self.route
  values=[int(r['maker'],16),int(app or AGGREGATOR,16),int(strategy or '0x'+'11'*32,16),
          int(token or r['token_out'],16),amount]
  return '0x47d72768'+b''.join(v.to_bytes(32,'big') for v in values).hex()
 def test_push_updates_price_without_hash_or_rpc(self):
  from unittest.mock import patch
  from c7_state_bridge import identity
  b=self.bridge();key=identity(self.route);token=self.route['token_out']
  old=b.allocations[key][token]
  with patch('hub_state.storage_key',side_effect=AssertionError('hot path hash subprocess')):
   result=b.apply_hub_push(self.push(),sender='0x'+'12'*20)
  self.assertTrue(result['allocation_updated'])
  self.assertEqual(b.allocations[key][token],old+7)
  self.assertEqual(b.inventory[token],0)
 def test_push_router_debit_and_underflow_rollback(self):
  from c9_router import C9
  b=self.bridge(10)
  b.apply_hub_push(self.push(),sender=C9)
  self.assertEqual(b.inventory[self.route['token_out']],3)
  before=self.snapshot(b)
  with self.assertRaisesRegex(ValueError,'underflow'):b.apply_hub_push(self.push(),sender=C9)
  self.assertEqual(self.snapshot(b),before)
 def test_foreign_strategy_push_keeps_router_flow(self):
  from c9_router import C9
  for arguments in [dict(strategy='0x'+'22'*32),dict(app='0x'+'33'*20)]:
   b=self.bridge(10);old=copy.deepcopy(b.allocations)
   result=b.apply_hub_push(self.push(**arguments),sender=C9)
   self.assertFalse(result['allocation_updated'])
   self.assertEqual(b.allocations,old)
   self.assertEqual(b.inventory[self.route['token_out']],3)
 def test_missing_hash_index_rejected(self):
  b=self.bridge();b.hash_index_complete=False
  with self.assertRaisesRegex(ValueError,'strategy hashes'):b.apply_hub_push(self.push(),sender='0x'+'12'*20)
 def pull(self,amount=7,recipient=None):
  from c9_router import C9
  values=[int(self.route['maker'],16),int('11'*32,16),int(self.route['token_out'],16),amount,int(recipient or C9,16)]
  return '0xb00bbd10'+b''.join(v.to_bytes(32,'big') for v in values).hex()
 def test_pull_namespace_and_router_credit(self):
  from hub_state import AGGREGATOR
  from c7_state_bridge import identity
  b=self.bridge();key=identity(self.route);token=self.route['token_out'];old=b.allocations[key][token]
  self.assertTrue(b.apply_hub_pull(self.pull(),AGGREGATOR)['allocation_updated'])
  self.assertEqual(b.allocations[key][token],old-7)
  self.assertEqual(b.inventory[token],7)
  self.assertFalse(b.apply_hub_pull(self.pull(),'0x'+'22'*20)['allocation_updated'])
  self.assertEqual(b.allocations[key][token],old-7)
  self.assertEqual(b.inventory[token],14)
 def test_pull_overflow_rolls_back_allocation(self):
  from hub_state import AGGREGATOR
  b=self.bridge((1<<256)-1);before=self.snapshot(b)
  with self.assertRaisesRegex(ValueError,'overflow'):b.apply_hub_pull(self.pull(),AGGREGATOR)
  self.assertEqual(self.snapshot(b),before)
 def test_pull_to_other_recipient_does_not_change_inventory(self):
  from hub_state import AGGREGATOR
  b=self.bridge(10)
  b.apply_hub_pull(self.pull(recipient='0x'+'33'*20),AGGREGATOR)
  self.assertEqual(b.inventory[self.route['token_out']],10)
if __name__=='__main__':unittest.main()
