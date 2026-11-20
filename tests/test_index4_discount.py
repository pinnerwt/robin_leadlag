import copy,json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from index4_fee import caller_discount,discounted_fee
from index4_local import PoolState,POOL
class DiscountTest(unittest.TestCase):
 def test_profile_precedence_matches_helper_bytecode(self):
  cases=json.loads(Path('reports/amm/routera3d-index4-caller-adjustment-probe.json').read_text())['cases'];self.assertEqual(len(cases),18)
  for c in cases:
   caller,origin=c['caller_profile'],c['origin_profile']
   value=caller_discount((caller[0]<<8)|int(caller[1]),(origin[0]<<8)|int(origin[1]),caller_pool_word=caller[2],origin_pool_word=origin[2],same_origin=c['same_origin'])
   self.assertEqual(value,c['value'])
 def test_effective_fee_curve_and_base_cache_match_bytecode(self):
  seed=json.loads(Path('reports/amm/routera3d-index4-ticks-dependencies.json').read_text());source=json.loads(Path('reports/amm/routera3d-index4-crossing-probe.json').read_text());report=json.loads(Path('reports/amm/routera3d-index4-adjusted-fee-probe.json').read_text());self.assertEqual(len(report['cases']),28)
  initial=PoolState.initialize(seed,bitmap_words=[seed['tick_initialization']['bitmap_word']],caller_discount=0)
  tx=source['cases'][0]['transaction'];limit=int.from_bytes(bytes.fromhex(tx['data'][10:])[96:128],'big')
  for c in report['cases']:
   with self.subTest(cache=c['stored'],discount=c['adjustment']):
    tx=source['cases'][c['side']]['transaction'];limit=int.from_bytes(bytes.fromhex(tx['data'][10:])[96:128],'big');zero=source['cases'][c['side']]['zero'];amount=source['cases'][c['side']]['amount']
    self.assertEqual(discounted_fee(263,c['adjustment']),c['fee'])
    state=copy.deepcopy(initial);state.caller_discount=c['adjustment'];state.fee_cache[state.last_block]=c['stored']
    if c['fee']==0:
     self.assertIn('unknown slot',c['result']['error'])
     with self.assertRaisesRegex(ValueError,'pool fallback'):state.preview_exact_input(block=tx['sequence'],timestamp=tx['timestamp'],zero=zero,amount=amount,limit=limit)
     continue
    out=state.preview_exact_input(block=tx['sequence'],timestamp=tx['timestamp'],zero=zero,amount=amount,limit=limit)
    self.assertEqual(out['fee'],c['fee']);self.assertEqual(out['state'].fee_cache[state.last_block],263)
    transfers=[x for x in c['result']['calls'] if x['data'].startswith('0xa9059cbb')];self.assertEqual(len(transfers),1)
    self.assertEqual(-out['result']['amount1' if zero else 'amount0'],int(transfers[0]['data'][-64:],16))
    writes=[w for w in c['result']['storage_writes'] if w['address']==POOL and int(w['slot'],16)==6]
    self.assertEqual(out['result']['sqrt'],int(writes[-1]['value'],16)&((1<<160)-1))
 def test_unknown_origin_not_assumed_zero(self):
  with self.assertRaises(ValueError):caller_discount(0,None)
  self.assertEqual(caller_discount(100<<8,None),100)
  with self.assertRaises(ValueError):caller_discount(1,0)
