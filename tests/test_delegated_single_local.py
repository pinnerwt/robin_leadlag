import copy,json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from delegated_single_local import preview
from v3_state import State

class SingleLocalTest(unittest.TestCase):
 def setUp(self):
  self.cases=json.loads(Path('reports/amm/delegated-single-callback-probe.json').read_text())['cases']
  self.case=next(c for c in self.cases if c['tx']['tx'].startswith('0x7b104a4de6'))
  self.metadata={p['pool']:p for p in json.loads(Path('captures/startup-v9-quotes.json').read_text())['pools']}
  self.curves={a:State.load(p) for a,p in self.metadata.items()}
 def test_recorded_first_updates_without_suffix_state(self):
  before=copy.deepcopy(self.curves)
  r=preview(self.case['tx']['data'],self.curves,self.metadata,self.metadata)
  self.assertEqual(self.curves,before)
  self.assertEqual(len(r['fills']),1);fill=r['fills'][0]
  call=self.case['result']['calls'][0]
  self.assertEqual(fill['pool'],call['to'])
  self.assertEqual(fill['amount1'],int.from_bytes(bytes.fromhex(call['data'][10:])[64:96],'big'))
  self.assertGreater(r['curves'][fill['pool']].sqrt,before[fill['pool']].sqrt)
  self.assertEqual(len(r['skipped_suffix']),2)
  self.assertEqual(set(r['stale_dependencies']),{a['target'] for a in self.case['plan']['actions'][1:]})
  self.assertTrue(r['transaction_success_assumed']);self.assertFalse(r['conditions_evaluated'])
 def test_recorded_later_requires_upstream(self):
  case=next(c for c in self.cases if c['tx']['tx'].startswith('0x9bc1e70a53'))
  with self.assertRaisesRegex(ValueError,'missing upstream pool state'):preview(case['tx']['data'],self.curves,self.metadata,self.metadata)
 def test_recorded_suffix_is_not_silently_skipped(self):
  before=copy.deepcopy(self.curves)
  recorded=set(self.metadata)|{self.case['plan']['actions'][-1]['target']}
  with self.assertRaisesRegex(ValueError,'missing upstream pool state'):preview(self.case['tx']['data'],self.curves,self.metadata,recorded)
  self.assertEqual(self.curves,before)
 def test_v4_route_remains_unsupported(self):
  with self.assertRaisesRegex(ValueError,'unverified single-route action'):preview(self.cases[0]['tx']['data'],self.curves,self.metadata,self.metadata)
 def test_saved_pool_bytecode_matches_output_and_sqrt(self):
  evidence=json.loads(Path('reports/amm/delegated-single-curve-probe.json').read_text())
  r=preview(self.case['tx']['data'],self.curves,self.metadata,self.metadata);fill=r['fills'][0]
  self.assertEqual(fill,evidence['expected'])
  actual=evidence['result'];self.assertIsNone(actual['error']);self.assertEqual(len(actual['calls']),1)
  call=actual['calls'][0];self.assertEqual(call['to'],self.metadata[fill['pool']]['tokens'][0])
  self.assertEqual(call['data'][:10],'0xa9059cbb');self.assertEqual(int(call['data'][-64:],16),-fill['amount0'])
  writes=[w for w in actual['storage_writes'] if w['address']==fill['pool'] and int(w['slot'],16)==0]
  self.assertEqual(int(writes[-1]['value'],16)&((1<<160)-1),fill['sqrt'])
