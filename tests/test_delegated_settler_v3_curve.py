import json,unittest
from pathlib import Path
class SettlerV3CurveTest(unittest.TestCase):
 def test_actual_transfer_and_slot0_match_local_curve(self):
  e=json.loads(Path('reports/amm/delegated-settler-v3-curve.json').read_text());r=e['result'];q=e['expected']
  self.assertIsNone(r['error']);self.assertEqual(len(r['calls']),1)
  call=r['calls'][0];self.assertEqual(call['to'],'0x5fc5360d0400a0fd4f2af552add042d716f1d168')
  self.assertEqual(call['data'][:10],'0xa9059cbb');self.assertEqual(int(call['data'][-64:],16),-q['amount1'])
  slot0=[w for w in r['storage_writes'] if w['address']==e['tx']['to'] and w['slot']=='0x0'][-1]
  value=int(slot0['value'],16);self.assertEqual(value&((1<<160)-1),q['sqrt'])
  tick=(value>>160)&((1<<24)-1);tick=tick-(1<<24) if tick&(1<<23) else tick
  self.assertEqual(tick,q['tick'])
 def test_actual_pool_return_with_explicit_synthetic_payment(self):
  e=json.loads(Path('reports/amm/delegated-settler-v3-curve-settled.json').read_text());r=e['result'];q=e['expected']
  self.assertIsNone(r['error']);self.assertTrue(r['execution_success']);self.assertEqual(r['calls'],[])
  d=bytes.fromhex(r['output'][2:]);self.assertEqual(len(d),64)
  self.assertEqual(int.from_bytes(d[:32],'big',signed=True),q['amount0'])
  self.assertEqual(int.from_bytes(d[32:],'big',signed=True),q['amount1'])
  self.assertTrue(e['synthetic_getters'])
  selectors=[c['data'][:10] for stage in e['stages'] for c in stage['calls']]
  self.assertIn('0xfa461e33',selectors);self.assertIn('0x70a08231',selectors)
