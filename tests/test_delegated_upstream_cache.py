import json,unittest
from pathlib import Path
class UpstreamCacheTest(unittest.TestCase):
 def test_explicit_cache_values_expose_missing_caller_profile(self):
  e=json.loads(Path('reports/amm/delegated-upstream-cache-probe.json').read_text())
  self.assertEqual([c['synthetic_fee_cache'] for c in e['cases']],[17,242,1000])
  for c in e['cases']:
   self.assertTrue(any(any(x['data'].startswith('0xb46c70b2') for x in stage['calls']) for stage in c['stages']))
   self.assertIn('unknown slot',c['result']['error'])
   self.assertIn('54941b97a33f62ca45c9711ddba898e47efea4e1cc134ce5296653be2ef2d64a',c['result']['error'])
 def test_isolated_curve_matches_bytecode_for_three_fees(self):
  v=json.loads(Path('reports/amm/delegated-upstream-curve-validation.json').read_text())
  e=json.loads(Path('reports/amm/delegated-upstream-cache-discount-0-no-rewards-skip-post-hook.json').read_text())
  self.assertTrue(e['synthetic_post_hook_noop']);self.assertEqual(e['synthetic_discount'],0)
  for model,case in zip(v['cases'],e['cases']):
   actual=case['result'];self.assertIsNone(actual['error']);self.assertEqual(len(actual['calls']),1)
   transfer=actual['calls'][0];self.assertEqual(transfer['data'][:10],'0xa9059cbb')
   self.assertEqual(int(transfer['data'][-64:],16),-model['expected']['amount0'])
   self.assertEqual(model['charged_fee'],case['synthetic_fee_cache'])
   writes=[w for w in actual['storage_writes'] if w['address']==v['pool'] and int(w['slot'],16)==6]
   self.assertEqual(int(writes[-1]['value'],16)&((1<<160)-1),model['expected']['sqrt'])
 def test_second_pool_requires_observation_and_matches_isolated_curve(self):
  prefix='reports/amm/delegated-upstream-cache-leg2-discount-0-no-rewards-skip-post-hook'
  baseline=json.loads(Path(prefix+'.json').read_text())
  for case in baseline['cases']:self.assertIn('unknown slot',case['result']['error']);self.assertIn('0x393',case['result']['error'])
  e=json.loads(Path(prefix+'-synthetic-observation.json').read_text())
  v=json.loads(Path('reports/amm/delegated-upstream-leg2-curve-validation.json').read_text())
  self.assertTrue(v['synthetic_observation']);self.assertEqual([c['charged_fee'] for c in v['cases']],[17,511,1000])
  for expected,case in zip(v['cases'],e['cases']):
   self.assertIn('0x393',case['synthetic_observations'])
   actual=case['result'];self.assertIsNone(actual['error'])
   transfer=actual['calls'][0];self.assertEqual(transfer['to'],'0x0bd7d308f8e1639fab988df18a8011f41eacad73')
   self.assertEqual(int(transfer['data'][-64:],16),-expected['expected']['amount0'])
   writes=[w for w in actual['storage_writes'] if w['address']==v['pool'] and int(w['slot'],16)==6]
   self.assertEqual(int(writes[-1]['value'],16)&((1<<160)-1),expected['expected']['sqrt'])
