import json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from delegated_unlock_plan import inspect
class DelegatedEncodingTest(unittest.TestCase):
 def test_controlled_compressed_mutations_match_expanded_plan(self):
  cases=json.loads(Path('reports/amm/delegated-encoding-probe.json').read_text())['cases']
  self.assertEqual(len(cases),5)
  for c in cases:
   self.assertIsNone(c['result']['error']);self.assertEqual(len(c['result']['calls']),1)
   plan=inspect(c['result']['calls'][0]['data']);first=plan['strategies'][0]
   self.assertEqual([a['kind'] for a in first['actions']],[4,1,1,0])
   if c['kind']=='first_amount':self.assertEqual(first['input_amount'],c['value'])
   else:self.assertEqual(first['actions'][1 if c['value']==1 else 2]['target'],c['replacement'])
 def test_all_four_payloads_and_truncation(self):
  cases=json.loads(Path('reports/amm/delegated-router-callback-probe.json').read_text())['cases']
  self.assertEqual([len(inspect(c['callback'])['strategies']) for c in cases],[4,2,2,3])
  for c in cases:
   with self.assertRaises(ValueError):inspect(c['callback'][:400])
