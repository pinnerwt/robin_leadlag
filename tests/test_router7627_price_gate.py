import json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path('scripts').resolve()))
from router7627_price_gate import branch
class PriceGateTest(unittest.TestCase):
 def test_six_actual_boundaries(self):
  for row in json.loads(Path('reports/amm/router7627-price-boundaries.json').read_text())['cases']:
   p=branch(row['price'],1<<96);r=row['result'];self.assertIsNone(r['error']);self.assertEqual(p['ratio'],row['price']);self.assertEqual(bool(p['branch']),bool(r['calls']))
 def test_saved_getter_noop_and_ratio(self):
  for row in json.loads(Path('reports/amm/router7627-local-getters.json').read_text())['cases']:
   r=row['result'];returns=r['execution_returns'];a=int(next(x['output'][2:66] for x in returns if x['selector']=='0x3850c7bd'),16);b=int(next(x['output'] for x in returns if x['selector']=='0x1e2eaeaf'),16)&((1<<160)-1);p=branch(a,b);self.assertEqual(p['branch'],0);self.assertTrue(r['execution_success']);self.assertEqual(r['calls'],[]);comparison=next(x for x in r['control_ops'] if x['pc']==11373);self.assertEqual(p['ratio'],int(comparison['a']))
