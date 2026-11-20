import json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path('scripts').resolve()))
from variant_v3_checkpoint import load as load_v3
from v4_pool_state import load as load_v4
from v3_state import tick_sqrt
from router7627_forward_limit import limit
from router7627_second_leg import POOL
from router7627_credit import MANAGER,USDG
class ForwardLimitTest(unittest.TestCase):
 def test_single_interval_matches_and_crossing_rejected(self):
  seed=json.loads(Path('captures/startup-v9-dependencies.json').read_text());key=dict(currency0='0x'+'00'*20,currency1=USDG,fee=0x800000,tick_spacing=1,hooks='0x987e330f00b79864a07fe81dfac344d0078abcc0')
  for shift in (2,50):
   name=f'reports/amm/router7627-local-getters-shift-{shift}-inventory-1000000000000000000-unlock.json'
   for row in json.loads(Path(name).read_text())['cases']:
    v3=load_v3(seed['accounts'][POOL]['storage'],100,1);v4=load_v4(seed['accounts'][MANAGER]['storage'],key,effective_lp_fee=40,bitmap_words=range(-788,-784))
    # Explicit synthetic price/tick and unchanged liquidity: formula comparison,
    # not proof of historical consistency across prior price movement.
    v4.sqrt=int(row['price_intervention']['synthetic'],16)&((1<<160)-1);v4.tick=tick_sqrt(v4.sqrt)
    if shift==50:
     with self.assertRaisesRegex(ValueError,'crossing solver'):limit(v3,v4)
    else:
     c=row['result']['calls'][0];self.assertEqual(c['to'],MANAGER);self.assertTrue(c['data'].startswith('0xf3cd914c'));expected=int(c['data'][458:522],16);self.assertEqual(limit(v3,v4),expected)
