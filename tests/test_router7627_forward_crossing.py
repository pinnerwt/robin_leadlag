import copy,json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path('scripts').resolve()))
from variant_v3_checkpoint import load as load_v3
from v4_pool_state import load as load_v4
from router7627_forward_crossing import optimize
from router7627_second_leg import POOL
from router7627_credit import MANAGER,USDG
class CrossingTest(unittest.TestCase):
 def test_all_optimizer_iterations_match_trace(self):
  seed=json.loads(Path('captures/startup-v9-dependencies.json').read_text());key=dict(currency0='0x'+'00'*20,currency1=USDG,fee=0x800000,tick_spacing=1,hooks='0x987e330f00b79864a07fe81dfac344d0078abcc0')
  for shift in (50,100):
   name=f'reports/amm/router7627-local-getters-shift-{shift}-inventory-1000000000000000000-unlock.json'
   for row in json.loads(Path(name).read_text())['cases']:
    a=load_v3(seed['accounts'][POOL]['storage'],100,1);b=load_v4(seed['accounts'][MANAGER]['storage'],key,effective_lp_fee=40,bitmap_words=range(-788,-784));b.sqrt=int(row['price_intervention']['synthetic'],16)&((1<<160)-1);before=copy.deepcopy((a,b))
    # Reproduce this explicitly inconsistent getter-only research composition.
    got=optimize(a,b);self.assertEqual((a,b),before);ops=row['result']['math_ops']
    candidates=[int(c['b']) for c in ops if c['pc']==9657 and c['a']=='999869' and int(c['b'])>10**20]
    nets=[int(c['a']) for c in ops if c['pc']==18433]
    self.assertEqual([c['candidate'] for c in got['iterations']],candidates);self.assertEqual([c['usdg_net'] for c in got['iterations'] if 'usdg_net' in c],nets)
    actual=row['result']['calls'][0];self.assertEqual(got['limit'],int(actual['data'][458:522],16));self.assertFalse(got['execution_complete'])
    with self.assertRaisesRegex(ValueError,'iteration bound'):optimize(a,b,max_steps=1)
    a.ticks={}
    with self.assertRaisesRegex(ValueError,'unknown initialized'):optimize(a,b)
