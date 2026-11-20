import json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from index4_pool_state import load
POOL='0x7615926023bb149f36095645c2a81dc367d39750'
class Index4StateTest(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.seed=json.loads(Path('reports/amm/routera3d-index4-ticks-dependencies.json').read_text())
  cls.report=json.loads(Path('reports/amm/routera3d-index4-crossing-probe.json').read_text())
 def state(self,fee):return load(self.seed['accounts'][POOL]['storage'],effective_fee=fee,bitmap_words=[self.seed['tick_initialization']['bitmap_word']])
 def test_real_bytecode_parity_including_both_crossing_partial_fills(self):
  self.assertEqual(self.seed['anchor']['hash'],self.report['anchor']['hash']);crossed=0
  for case in self.report['cases']:
   with self.subTest(tx=case['transaction']['tx']):
    r=case['stages'][-1];self.assertTrue(r['execution_success']);self.assertEqual(r['calls'],[])
    state=self.state(case['fee']);data=bytes.fromhex(case['transaction']['data'][10:]);limit=int.from_bytes(data[96:128],'big')
    result=state.swap(case['zero'],case['amount'],limit,True)
    out=bytes.fromhex(r['output'][2:]);actual=[int.from_bytes(out[i:i+32],'big',signed=True) for i in (0,32)]
    self.assertEqual([result['amount0'],result['amount1']],actual)
    writes={int(w['slot'],16):int(w['value'],16) for w in r['storage_writes'] if w['address']==POOL}
    tick=(writes[6]>>160)&((1<<24)-1);tick=tick-(1<<24) if tick&(1<<23) else tick
    self.assertEqual((result['sqrt'],result['tick']),(writes[6]&((1<<160)-1),tick))
    if result['steps']>1:
     crossed+=1;self.assertGreater(result['unfilled'],0)
     self.assertEqual(result['liquidity'],writes[13]&((1<<128)-1))
     self.assertEqual(result['unfilled'],case['amount']-actual[0 if case['zero'] else 1])
  self.assertEqual(crossed,2)
 def test_unknown_bitmap_and_tick_fail_closed(self):
  state=self.state(263);state.bitmap={}
  with self.assertRaisesRegex(ValueError,'unknown bitmap'):state.swap(False,10**9)
  state=self.state(263);state.ticks={}
  with self.assertRaisesRegex(ValueError,'unknown initialized tick'):state.swap(False,10**12)
