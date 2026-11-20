import json,unittest
from pathlib import Path
class UpstreamIndexFourTest(unittest.TestCase):
 def test_actual_getters_match_raw_route_metadata(self):
  e=json.loads(Path('reports/amm/delegated-upstream-index4-probe.json').read_text())
  cases=json.loads(Path('reports/amm/delegated-single-callback-probe.json').read_text())['cases']
  c=next(c for c in cases if c['tx']['tx'].startswith('0x9bc1e70a'))
  for i,a in enumerate(c['plan']['actions'][:2]):
   results=e['results'][i*5:i*5+5]
   for r in results:self.assertIsNone(r['error']);self.assertTrue(r['execution_success']);self.assertEqual(r['calls'],[])
   self.assertEqual(int(results[0]['output'],16),int(a['currency0'],16))
   self.assertEqual(int(results[1]['output'],16),int(a['currency1'],16))
   self.assertEqual(int(results[4]['output'],16),a['spacing'])
 def test_missing_fee_cache_is_not_zero_filled(self):
  e=json.loads(Path('reports/amm/delegated-upstream-index4-probe.json').read_text())
  self.assertTrue(any(any(c['data'].startswith('0xd3e6bf58') for c in r['calls']) for r in e['stages']))
  self.assertIn('unknown slot',e['stages'][-1]['error'])
  self.assertIn('4da95083e7a445c175b3bd68beb7bf9062a0e720259428610183dbbab4cafd4a',e['stages'][-1]['error'])
