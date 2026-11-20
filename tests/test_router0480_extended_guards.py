import json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path('scripts').resolve()))
from router0480_guards import inspect,evaluate
from router0480_extended_guards import price_from_word

class ExtendedGuardsTest(unittest.TestCase):
 def test_actual_getter_intents(self):
  for row in json.loads(Path('reports/amm/router0480-remaining-guards.json').read_text())['cases']:
   g=next(g for g in inspect(row['original_tx']['data'])['guards'] if g['opcode']==row['opcode']);call=row['result']['calls'][0]
   self.assertEqual(g.get('manager',g['pool']),call['to']);self.assertEqual(g['getter_data'],call['data'])
   if row['opcode']==184:self.assertIn('unknown account',row['baseline']['error'])
 def test_eighteen_actual_boundaries(self):
  rows=json.loads(Path('reports/amm/router0480-remaining-boundaries.json').read_text())['cases'];self.assertEqual(len(rows),18)
  for row in rows:
   price=price_from_word(row['opcode'],row['synthetic_packed_word']);self.assertEqual(price,row['price']);g=dict(pool='test',side=row['side'],limit=row['limit']);skip=evaluate(dict(guards=[g]),{'test':price})['skip'];r=row['result'];self.assertIsNone(r['error'])
   self.assertEqual(skip,r['execution_success']);self.assertEqual(len(r['calls']),0 if skip else 1)
   if not skip:self.assertTrue(r['calls'][0]['data'].startswith('0x70a08231'))
 def test_disabled_and_invalid_words(self):
  self.assertIsNone(price_from_word(184,1));self.assertIsNone(price_from_word(172,0))
  with self.assertRaises(ValueError):price_from_word(184,1<<256)
