import copy,json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path('scripts').resolve()))
from router7627_reverse_limit import limit
from variant_v3_checkpoint import load as load_v3
from v4_pool_state import load as load_v4
from router7627_second_leg import POOL
from router7627_credit import MANAGER,USDG
class LimitTest(unittest.TestCase):
 def test_different_prices_match_actual_optimizer(self):
  seed=json.loads(Path('captures/startup-v9-dependencies.json').read_text());key=dict(currency0='0x'+'00'*20,currency1=USDG,fee=0x800000,tick_spacing=1,hooks='0x987e330f00b79864a07fe81dfac344d0078abcc0');slot='0xa652248898f7392773fb86e84bf1ef4cf17b449600f2d309595c039285782ad8'
  observed=[]
  for shift in (-3,-7):
   name=f'reports/amm/router7627-local-getters-shift-{shift}-inventory-1000000000000000000-unlock-state-shift.json'
   for row in json.loads(Path(name).read_text())['cases']:
    storage=copy.deepcopy(seed['accounts'][MANAGER]['storage']);storage[slot]=row['price_intervention']['synthetic']
    v3=load_v3(seed['accounts'][POOL]['storage'],100,1);v4=load_v4(storage,key,effective_lp_fee=40,bitmap_words=range(-788,-784))
    actual=row['result']['calls'][0];self.assertEqual(actual['to'],POOL);self.assertTrue(actual['data'].startswith('0x128acb08'))
    expected=int(actual['data'][202:266],16);self.assertEqual(limit(v3,v4),expected);observed.append(expected)
    v4.bitmap={}
    with self.assertRaisesRegex(ValueError,'missing optimizer bitmap'):limit(v3,v4)
  self.assertEqual(len(set(observed)),2)
