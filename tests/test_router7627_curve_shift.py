import json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path('scripts').resolve()))
from v4_pool_state import load
from variant_v3_checkpoint import load as load_v3
from router7627_credit import MANAGER,USDG
from router7627_second_leg import POOL
from router7627_forward_crossing import optimize
class CurveShiftTest(unittest.TestCase):
 def test_curve_intervention_and_new_boundary_coverage(self):
  seed=json.loads(Path('captures/startup-v9-dependencies.json').read_text());key=dict(currency0='0x'+'00'*20,currency1=USDG,fee=0x800000,tick_spacing=1,hooks='0x987e330f00b79864a07fe81dfac344d0078abcc0')
  for shift in (2,5,10):
   for row in json.loads(Path(f'reports/amm/router7627-local-getters-shift-{shift}-inventory-1000000000000000000-unlock-curve-shift.json').read_text())['cases']:
    v4=load(seed['accounts'][MANAGER]['storage'],key,effective_lp_fee=40,bitmap_words=range(-788,-784));wanted=v4.sqrt*(10000+shift)//10000;expected=v4.swap(False,1<<200,wanted,commit=True)
    self.assertEqual(row['price_intervention']['curve'],expected);packed=int(row['price_intervention']['synthetic'],16);self.assertEqual(packed&((1<<160)-1),v4.sqrt);self.assertEqual((packed>>160)&((1<<24)-1),v4.tick%(1<<24));self.assertIsNone(row['result']['error'])
    v3=load_v3(seed['accounts'][POOL]['storage'],100,1)
    if shift==2:
     predicted=optimize(v3,v4);actual=row['result']['calls'][0];self.assertEqual(predicted['limit'],int(actual['data'][458:522],16))
    else:
     boundary,initialized=v4.next_tick(v4.tick,True);self.assertEqual(boundary,-201216);self.assertFalse(initialized)
     predicted=optimize(v3,v4)
     actual=row['result']['calls'][0];self.assertEqual(predicted['limit'],int(actual['data'][458:522],16))
     candidates=[int(c['b']) for c in row['result']['math_ops'] if c['pc']==9657 and c['a']=='999869' and int(c['b'])>10**20]
     self.assertEqual([c['candidate'] for c in predicted['iterations']],candidates)
     boundary_step=next(c for c in predicted['iterations'] if c.get('v4_boundary')==-201216)
     if shift==5:
      self.assertEqual(boundary_step['v4_output'],1550916878);self.assertEqual(boundary_step['v3_effective_input'],1550761786)
     broken=load(seed['accounts'][MANAGER]['storage'],key,effective_lp_fee=40,bitmap_words=range(-788,-784));broken.sqrt=v4.sqrt;broken.tick=v4.tick;broken.liquidity=v4.liquidity
     broken.bitmap[-201216>>8]|=1<<(-201216&255)
     with self.assertRaisesRegex(ValueError,'initialized V4 crossing'):optimize(v3,broken)
