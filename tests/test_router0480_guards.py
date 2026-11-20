import json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path('scripts').resolve()))
from router0480_guards import inspect,evaluate
class GuardTest(unittest.TestCase):
 def test_actual_comparisons_and_skip(self):
  r=json.loads(Path('reports/amm/router0480-local-getters.json').read_text());plan=inspect(r['tx']['data']);prices={};ops=r['result']['control_ops'];comparisons=[o for o in ops if o['pc'] in (20947,18925)]
  self.assertEqual(len(plan['guards']),len(comparisons))
  for g,o in zip(plan['guards'],comparisons):
   self.assertEqual(g['limit'],int(o['b']));prices[g['pool']]=int(o['a']);self.assertEqual(o['opcode'],16 if g['side'] else 17)
  self.assertEqual(evaluate(plan,prices),dict(skip=True,failed_guard=2));self.assertTrue(r['result']['execution_success']);self.assertEqual(r['result']['calls'],[])
 def test_equal_boundary_and_missing_price(self):
  r=json.loads(Path('reports/amm/router0480-local-getters.json').read_text());p=inspect(r['tx']['data']);prices={g['pool']:g['limit'] for g in p['guards']};self.assertFalse(evaluate(p,prices)['skip'])
  with self.assertRaises(ValueError):evaluate(p,{})
 def test_actual_equal_boundary_continues_to_inventory(self):
  r=json.loads(Path('reports/amm/router0480-guard-boundary.json').read_text());self.assertEqual(r['new_limit'],3384945089467101610466034);self.assertFalse(r['local_verdict']['skip']);self.assertIsNone(r['result']['error']);c=r['result']['calls'];self.assertEqual(len(c),1);self.assertEqual(c[0]['data'][:10],'0x70a08231');self.assertEqual(c[0]['to'],'0x5fc5360d0400a0fd4f2af552add042d716f1d168')
