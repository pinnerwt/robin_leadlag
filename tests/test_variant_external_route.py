import json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path('scripts').resolve()))
from variant_external_route import inspect,TARGET
class ExternalRouteTest(unittest.TestCase):
 def setUp(self):
  self.e=json.loads(Path('reports/amm/batch-unpinned-plans.json').read_text())['transactions'][0];self.p=json.loads(Path('captures/startup-v9-quotes.json').read_text())['pools']
 def test_original_route_identifies_recorded_pool(self):
  r=inspect(self.e['tx']['data'],self.p);self.assertEqual(r['external']['target'],TARGET);self.assertEqual(r['pools'],['0x69bfaf19c9f377bb306a89aed9f6b07e2c1a8d9a']);self.assertFalse(r['scope_verified'])
 def test_external_recipient_and_wrap_mutations_rejected(self):
  data=self.e['tx']['data'];a=self.e['plan']['actions'][1]['data'];raw=bytes.fromhex(a[2:]);changed=raw[:264]+bytes(32)+raw[296:]
  with self.assertRaises(ValueError):inspect(data.replace(a[2:],changed.hex()),self.p)
  a=self.e['plan']['actions'][2]['data'];bad=a.replace('d0e30db0','d0e30db1')
  with self.assertRaises(ValueError):inspect(data.replace(a[2:],bad[2:]),self.p)
 def test_corpus_audit_covers_observed_recorded_pool(self):
  from audit_batch_coverage import classify
  row=next(json.loads(line) for line in Path('reports/amm/optimistic-target-corpus.jsonl').read_text().splitlines() if json.loads(line)['tx']['tx']==self.e['tx']['tx'])
  # Missing entry code must remain a failure even when structural scope is known.
  r=classify(row['tx'],row['logs'],{'accounts':{}},{p['pool']:p for p in self.p})
  self.assertEqual(r['status'],'batch_unresolved');self.assertFalse(r['safe_to_skip'])
  route=r['structural_candidate']['whole_route'];self.assertEqual(route['recorded_pools'],r['observed_pools']);self.assertFalse(route['scope_verified'])
