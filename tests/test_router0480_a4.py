import json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path('scripts').resolve()))
from router0480_guards import inspect
from router0480_reserve_guard import failed
class A4Test(unittest.TestCase):
 def test_actual_six_boundaries(self):
  r=json.loads(Path('reports/amm/router0480-a4-boundaries.json').read_text());self.assertEqual(len(r['cases']),6)
  for row in r['cases']:
   g=inspect(row['tx']['data'])['guards'][0];skip=failed(g,r['reserves']);result=row['result'];comp=[o for o in result['control_ops'] if o['pc'] in (14430,14449)]
   self.assertEqual(len(comp),1);self.assertEqual(skip,int(comp[0]['a'])<int(comp[0]['b']))
   if skip:self.assertTrue(result['execution_success']);self.assertFalse(result['calls'])
   else:self.assertIn('unknown account',result['error'])
 def test_invalid_reserve_rejected(self):
  r=json.loads(Path('reports/amm/router0480-a4.json').read_text());g=inspect(r['tx']['data'])['guards'][0]
  for values in ((0,1),(1,1<<128),None):
   with self.assertRaises(ValueError):failed(g,values)
