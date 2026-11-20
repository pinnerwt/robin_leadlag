import copy,json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path('scripts').resolve()))
from delegated_batch_preview import preview_raw
import test_delegated_settler_local as fixtures
class BatchPreviewTest(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  fixtures.SettlerLocalTest.setUpClass();cls.state=fixtures.SettlerLocalTest.kw
  cls.tx=next(t for t in map(json.loads,Path('reports/amm/delegated-router-txs.jsonl').read_text().splitlines()) if t['tx'].startswith('0x99fa4228'))
  anchor=json.loads(Path('captures/startup-v9-quotes.json').read_text())['anchor']['hash'];cls.anchors={k:anchor for k in ('v4','hook','v3','inventory')}
 def test_raw_preview_matches_chain_and_marks_success_assumption(self):
  before=copy.deepcopy(self.state)
  r=preview_raw(self.tx['data'],bridge_state=self.state,anchors=self.anchors,usdg_balance=0,assume_success=True)
  self.assertEqual(r['v3_fill']['amount1'],-1454595);self.assertEqual(r['hook_fee']['net'],796969091046830)
  self.assertEqual(r['known_violations'],[dict(kind='settler_min_output',required=1473362,available=1454595),dict(kind='outer_router_min_output',required=1473362,available=1454595)])
  self.assertTrue(r['success_assumed']);self.assertFalse(r['complete_scope_verified']);self.assertEqual(self.state,before)
 def test_strict_failure_does_not_mutate(self):
  before=copy.deepcopy(self.state)
  with self.assertRaisesRegex(ValueError,'minimum output'):preview_raw(self.tx['data'],bridge_state=self.state,anchors=self.anchors,usdg_balance=0)
  self.assertEqual(self.state,before)
 def test_mixed_anchor_rejected_even_when_assuming_success(self):
  anchors=dict(self.anchors,hook='different')
  with self.assertRaisesRegex(ValueError,'checkpoint anchors'):preview_raw(self.tx['data'],bridge_state=self.state,anchors=anchors,usdg_balance=0,assume_success=True)
 def test_tail_uses_prior_usdg_inventory(self):
  r=preview_raw(self.tx['data'],bridge_state=self.state,anchors=self.anchors,usdg_balance=4000000-1454595)
  self.assertEqual(r['tail']['amount'],2156988);self.assertEqual(r['outer_router_receipt'],1843011);self.assertEqual(r['usdg_balance'],1)
  self.assertEqual(r['known_violations'],[]);self.assertFalse(r['execution_complete'])
 def test_actual_minimum_boundary_overrides_dust_reserve(self):
  e=json.loads(Path('reports/amm/delegated-settler-tail-callback-output-1473362.json').read_text())
  self.assertIsNone(e['result']['error']);call=e['result']['calls'][0]
  self.assertEqual(call['to'],'0x5fc5360d0400a0fd4f2af552add042d716f1d168')
  self.assertEqual(call['data'][:10],'0xa9059cbb');self.assertEqual(int(call['data'][-64:],16),1473362)
  self.assertEqual(int(call['data'][10:74],16),int('5399d94d2cab7c252a6034042e1917a0e5e17a18',16))
  r=preview_raw(self.tx['data'],bridge_state=self.state,anchors=self.anchors,usdg_balance=1473362-1454595)
  self.assertEqual(r['known_violations'],[]);self.assertEqual(r['outer_router_receipt'],1473362)
