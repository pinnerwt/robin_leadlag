import json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path('scripts').resolve()))
from router0480_guards import inspect,evaluate
from bootstrap_state import mapping
class A8Test(unittest.TestCase):
 def test_actual_slot_derivation_and_missing_state(self):
  r=json.loads(Path('reports/amm/router0480-a8.json').read_text());g=inspect(r['original_tx']['data'])['guards'][1];call=r['stages'][0]['calls'][0];self.assertEqual(call['to'],g['manager']);self.assertEqual(call['data'],g['getter']+mapping(int(g['pool'],16),6)[2:]);self.assertIn('unknown slot',r['result']['error'])
 def test_packed_price_mask_and_six_comparisons(self):
  r=json.loads(Path('reports/amm/router0480-a8-boundaries.json').read_text());self.assertEqual(len(r['cases']),6)
  for row in r['cases']:
   original=json.loads(Path('reports/amm/router0480-a8.json').read_text())['original_tx']['data'];g=dict(inspect(original)['guards'][1],side=row['side']);p={'guards':[g]};self.assertEqual(row['synthetic_packed_slot']&((1<<160)-1),row['price']);comp=[c for c in row['result']['control_ops'] if c['pc'] in (18925,20947)];self.assertEqual(len(comp),1);self.assertEqual(int(comp[0]['a']),row['price']);self.assertEqual(int(comp[0]['b']),g['limit']);v=evaluate(p,{g['pool']:row['price']})
   self.assertIsNone(row['result']['error'])
   if v['skip']:self.assertTrue(row['result']['execution_success']);self.assertFalse(row['result']['calls'])
   else:self.assertEqual(row['result']['calls'][0]['data'][:10],'0x70a08231')
