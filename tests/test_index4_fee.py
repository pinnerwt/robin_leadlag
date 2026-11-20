import json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from index4_fee import cached_fee,undiscounted_fee

def config(base=79,cap=7500,slope=8380000):return base|(cap<<24)|(slope<<48)
class Index4FeeTest(unittest.TestCase):
 def test_tick_counterfactuals_match_actual_callback(self):
  cases=json.loads(Path('reports/amm/routera3d-index4-fee-cache-probe.json').read_text())['cases']
  ticks=[c for c in cases if c['cached']=='tick_intervention'];self.assertEqual(len(ticks),18)
  self.assertTrue(any(c['signed_tick_delta']<0 for c in ticks));self.assertTrue(any(c['signed_tick_delta']==0 for c in ticks));self.assertTrue(any(c['signed_tick_delta']>0 for c in ticks))
  for c in ticks:self.assertEqual(undiscounted_fee(config(),c['tick'],*c['cumulatives'],600),c['fee'])
 def test_config_counterfactuals_and_cache(self):
  cases=json.loads(Path('reports/amm/routera3d-index4-fee-cache-probe.json').read_text())['cases']
  for c in cases:
   if type(c['cached']) is int:self.assertEqual(cached_fee(c['cached']),c['fee'])
   if c['cached']=='config_intervention':
    cfg=c['config'];result=c['result'];observed=next(x['output'] for x in result['execution_returns'] if x['selector']=='0x883bdbfd')
    raw=bytes.fromhex(observed[2:]);old,now=[int.from_bytes(raw[i:i+32],'big',signed=True) for i in (96,128)]
    self.assertEqual(undiscounted_fee(config(cfg['minimum'],cfg['maximum'],cfg['slope']),c['tick'],old,now,c['window_seconds']),c['fee'])
  self.assertIsNone(cached_fee(0))
 def test_reject_unknown_flags_and_wrap(self):
  with self.assertRaisesRegex(ValueError,'flags'):undiscounted_fee(config()|(1<<112),0,0,0,600)
  with self.assertRaisesRegex(ValueError,'wrap'):undiscounted_fee(config(),0,-(1<<55),(1<<55)-1,600)
  with self.assertRaises(ValueError):cached_fee(None)
