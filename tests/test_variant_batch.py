import copy,json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path('scripts').resolve()))
from preview_variant_v3_bridge import inputs
from variant_batch_preview import preview_raw
from variant_batch_route import inspect
class RawVariantTest(unittest.TestCase):
 def fixture(self):
  _,_,a,_=inputs();e=json.loads(Path('reports/amm/batch-unpinned-plans.json').read_text())['transactions'][1];p=a['pools']
  return e['tx']['data'],dict(curves={p[0]['pool']:a['upstream'],p[1]['pool']:a['downstream']},pools=p,anchors=a['anchors'],weth_balance=0,usdg_balance=0)
 def test_original_calldata_to_pool_state(self):
  data,a=self.fixture();before=copy.deepcopy(a);r=preview_raw(data,**a)
  self.assertEqual(a,before);self.assertEqual(r['downstream_fill']['amount1'],-1832682);self.assertEqual(len(r['curves']),2);self.assertEqual(r['known_violations'],[]);self.assertFalse(r['complete_scope_verified'])
  self.assertEqual(r['usdg_balance']+r['outer_router_receipt']+r['tail']['amount'],1832682)
 def test_mismatched_funding_and_extra_data_reject(self):
  data,a=self.fixture();plan=inspect(data,a['pools']);action=plan['holder']['actions'][0]['data'];raw=bytes.fromhex(action[2:]);changed='0x'+(raw[:68]+(plan['upstream']['amount']+1).to_bytes(32,'big')+raw[100:]).hex()
  bad=data.replace(action[2:],changed[2:]);self.assertNotEqual(bad,data)
  with self.assertRaisesRegex(ValueError,'funding'):preview_raw(bad,**a)
  with self.assertRaises(ValueError):preview_raw(data+'00',**a)
 def test_missing_bound_pool_rejects(self):
  data,a=self.fixture();a['curves'].pop(a['pools'][0]['pool'])
  with self.assertRaisesRegex(ValueError,'bound'):preview_raw(data,**a)
 def test_missing_state_is_not_committed(self):
  data,a=self.fixture();a['curves'][a['pools'][1]['pool']].bitmap={};before=copy.deepcopy(a)
  with self.assertRaises(ValueError):preview_raw(data,**a)
  self.assertEqual(before,a)
 def test_optimistic_mode_retains_minimum_violations(self):
  data,a=self.fixture();plan=inspect(data,a['pools']);action=plan['holder']['actions'][2]['data'];raw=bytes.fromhex(action[2:]);changed=(raw[:68]+bytes(32)+raw[100:]).hex();bad=data.replace(action[2:],changed)
  before=copy.deepcopy(a)
  with self.assertRaisesRegex(ValueError,'minimum'):preview_raw(bad,**a)
  self.assertEqual(before,a)
  r=preview_raw(bad,**a,assume_success=True);self.assertEqual({x['kind'] for x in r['known_violations']},{'settler_min_output','outer_router_min_output'});self.assertTrue(r['success_assumed'])
