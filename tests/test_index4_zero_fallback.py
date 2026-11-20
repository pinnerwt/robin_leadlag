import copy,json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from index4_local import PoolState,FACTORY
class ZeroFallbackTest(unittest.TestCase):
 def test_twenty_actual_pool_cases(self):
  seed=json.loads(Path('reports/amm/routera3d-index4-ticks-dependencies.json').read_text());report=json.loads(Path('reports/amm/routera3d-index4-zero-fallback-probe.json').read_text());source=json.loads(Path('reports/amm/routera3d-index4-crossing-probe.json').read_text())
  self.assertEqual(len(report['cases']),20);self.assertEqual(seed['anchor']['hash'],report['anchor_hash'])
  for c in report['cases']:
   with self.subTest(side=c['side'],cache=c['stored'],fallback=c['fallback']):
    patched=copy.deepcopy(seed);patched['accounts'][FACTORY]['storage'][report['factory_slot']]=hex(c['fallback'])
    state=PoolState.initialize(patched,bitmap_words=[seed['tick_initialization']['bitmap_word']],caller_discount=1000000)
    state.fee_cache[state.last_block]=c['stored'];ref=source['cases'][c['side']];tx=ref['transaction'];limit=int.from_bytes(bytes.fromhex(tx['data'][10:])[96:128],'big')
    out=state.preview_exact_input(block=tx['sequence'],timestamp=tx['timestamp'],zero=ref['zero'],amount=ref['amount'],limit=limit)
    self.assertEqual(out['callback_fee'],0);self.assertEqual(out['fee'],c['fallback']);self.assertEqual(out['base_fee'],263)
    self.assertEqual(out['state'].fee_cache[state.last_block],263);self.assertEqual(out['result'],c['expected'])
