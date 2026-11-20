import json,unittest
from pathlib import Path
class SettlerCurveTest(unittest.TestCase):
 def test_missing_first_pool_not_zero_filled(self):
  c=json.loads(Path('reports/amm/delegated-settler-curve.json').read_text())['cases'][0]
  self.assertEqual(c['curve_error'],'missing V4 slot0/liquidity')
  self.assertIsNone(c['curve_result']);self.assertIn('unknown slot',c['result']['error'])
 def test_actual_manager_delta_and_state_match_local_curve(self):
  c=json.loads(Path('reports/amm/delegated-settler-curve.json').read_text())['cases'][1]
  r=c['result'];q=c['curve_result'];self.assertIsNone(r['error']);self.assertEqual(r['calls'],[])
  hook=[x for x in r['execution_returns'] if x['selector']=='0xb47b2fb1' and x['result']=='Return']
  swaps=[x for x in r['execution_returns'] if x['selector']=='0xf3cd914c' and x['result']=='Return']
  self.assertEqual(len(hook),1);self.assertEqual(len(swaps),1)
  fee=int(hook[0]['output'][-64:],16);gross=-q['amount0'];packed=int(swaps[0]['output'],16)
  net=packed>>128;input_delta=(packed&((1<<128)-1))-(1<<128)
  self.assertEqual(gross,820349038648306);self.assertEqual(fee,23379947601476)
  self.assertEqual(net,gross-fee);self.assertEqual(net,796969091046830)
  self.assertEqual(input_delta,-q['amount1']);self.assertEqual(q['unfilled'],0)
  slot='0x616f6bb5d14b4089488c2e9c41fb465179ce70c86ff40c30fecdfba2c6978c35'
  write=next(w for w in r['storage_writes'] if w['slot']==slot)
  v=int(write['value'],16)
  self.assertEqual(v&((1<<160)-1),q['sqrt']);self.assertEqual((v>>160)&((1<<24)-1),q['tick'])
