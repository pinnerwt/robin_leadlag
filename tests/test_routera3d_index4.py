import copy,json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from routera3d_index4 import intent,preview,WETH,USDG
from index4_local import PoolState
class RouterIndex4Test(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.seed=json.loads(Path('reports/amm/routera3d-index4-blocks-dependencies.json').read_text())
  cls.state=PoolState.initialize(cls.seed,bitmap_words=[cls.seed['tick_initialization']['bitmap_word']],caller_discount=0)
  cls.docs=[json.loads(Path('reports/amm/routera3d-index4-bounds'+suffix+'-probe.json').read_text()) for suffix in ('','-limited')]
  cls.slot9=int(cls.seed['accounts']['0xe3c90972c6462bb4a4c75cf49dcf4189c5b42880']['storage']['0x9'],16)
 def test_both_directions_and_inventory_cap_against_router_bytecode(self):
  count=0
  for doc in self.docs:
   self.assertEqual(doc['anchor']['hash'],self.seed['anchor']['hash'])
   inv={WETH:doc['weth_inventory'],USDG:doc['usdg_inventory']}
   for c in doc['cases']:
    route=intent(c['transaction']['data'],0,inv);calls=c['result']['calls'];self.assertEqual(len(calls),1)
    data=bytes.fromhex(calls[0]['data'][10:]);words=[int.from_bytes(data[i:i+32],'big') for i in range(0,160,32)]
    self.assertEqual([int(route['zero']),route['amount'],route['limit']],words[1:4]);count+=1
  self.assertEqual(count,12)
 def test_local_fee_independent_of_hint_and_balances_not_mutated(self):
  for doc in self.docs:
   inv={WETH:doc['weth_inventory'],USDG:doc['usdg_inventory']};before=copy.deepcopy((self.state.curve,self.state.observations.records,self.state.fee_cache,inv))
   for c in doc['cases']:
    tx=c['transaction'];out=preview(self.state,tx['data'],0,inv,block=tx['sequence'],timestamp=tx['timestamp'],router_slot9=self.slot9)
    self.assertEqual(out['fee'],95);self.assertEqual(out['intent']['limit_fee_hint_ppm'],c['hint'])
    self.assertEqual(out['inventory'][WETH],inv[WETH]-out['result']['amount0']);self.assertEqual(out['inventory'][USDG],inv[USDG]-out['result']['amount1'])
    self.assertFalse(out['execution_state_complete'])
   self.assertEqual((self.state.curve,self.state.observations.records,self.state.fee_cache,inv),before)
 def test_expired_and_zero_hint_fail_closed(self):
  doc=self.docs[0];tx=doc['cases'][0]['transaction'];inv={WETH:doc['weth_inventory'],USDG:doc['usdg_inventory']}
  with self.assertRaisesRegex(ValueError,'zero hint'):intent(tx['data'][:-4]+'0000',0,inv)
  with self.assertRaisesRegex(ValueError,'outside block window'):preview(self.state,tx['data'],0,inv,block=tx['sequence']+2,timestamp=tx['timestamp'],router_slot9=self.slot9)
