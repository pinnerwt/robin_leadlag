import json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path('scripts').resolve()))
from router0480_profit import condition,evaluate
class ProfitTest(unittest.TestCase):
 def test_actual_router_boundaries(self):
  for end in (100,101,102):
   r=json.loads(Path(f'reports/amm/router0480-profit-1-{end}.json').read_text());p=evaluate(r['tx']['data'],100,end)
   self.assertIsNone(r['result']['error']);self.assertEqual(p['passes'],r['result']['execution_success']);self.assertEqual(p['required'],101);self.assertEqual(p['token'],'0x5fc5360d0400a0fd4f2af552add042d716f1d168')
 def test_overflow_and_invalid_inventory(self):
  r=json.loads(Path('reports/amm/router0480-profit-1-101.json').read_text());self.assertFalse(evaluate(r['tx']['data'],(1<<256)-1,(1<<256)-1)['passes'])
  with self.assertRaises(ValueError):evaluate(r['tx']['data'],-1,0)
 def test_original_zero_minimum(self):
  r=json.loads(Path('reports/amm/router0480-nested-paid.json').read_text());self.assertEqual(condition(r['tx']['data'])['minimum'],0)
  self.assertTrue(evaluate(r['tx']['data'],100,100)['passes']);self.assertFalse(evaluate(r['tx']['data'],100,99)['passes'])
