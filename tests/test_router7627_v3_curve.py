import json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path('scripts').resolve()))
from variant_v3_checkpoint import load
from router7627_second_leg import POOL,LIMIT
class V3CurveTest(unittest.TestCase):
 def test_actual_output_matches_local_integer_curve(self):
  seed=json.loads(Path('captures/startup-v9-dependencies.json').read_text());curve=load(seed['accounts'][POOL]['storage'],100,1);fill=curve.swap(False,2000000,LIMIT)
  report=json.loads(Path('reports/amm/router7627-local-getters-shift-50-inventory-1000000000000000000-unlock-synthetic-fill-v3.json').read_text())
  for row in report['cases']:
   r=row['result'];self.assertIsNone(r['error']);c=r['calls'][0];self.assertEqual(c['data'][:10],'0xa9059cbb');self.assertEqual(c['caller'].lower(),POOL);self.assertEqual(int(c['data'][-64:],16),-fill['amount0']);self.assertEqual(fill['amount1'],2000000);self.assertEqual(fill['unfilled'],0);self.assertFalse(r['execution_success'])
 def test_callback_reaches_transient_debt_read(self):
  report=json.loads(Path('reports/amm/router7627-local-getters-shift-50-inventory-1000000000000000000-unlock-synthetic-fill-v3-transfer-balance.json').read_text())
  for row in report['cases']:
   r=row['result'];self.assertIsNone(r['error']);self.assertTrue(row['synthetic_v3_balance']);self.assertTrue(any(c['data'].startswith('0xfa461e33') for c in r['execution_calls']));self.assertEqual(r['calls'][0]['data'],'0xf135baaafa47c3fbc6da32693cc210992343a11434b43c80b13805a65ec6bb65ee9c8b53');self.assertFalse(r['execution_success'])
