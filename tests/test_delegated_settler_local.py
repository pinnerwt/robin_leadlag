import copy,json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path('scripts').resolve()))
from delegated_settler_local import preview
from v4_pool_state import load
from v3_state import State
class SettlerLocalTest(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  seed=json.loads(Path('captures/startup-v9-dependencies.json').read_text());cls.plan=json.loads(Path('reports/amm/delegated-holder-plans.json').read_text())['transactions'][1]['plan']
  c=json.loads(Path('reports/amm/delegated-settler-curve.json').read_text())['cases'][1]
  meta=next(p for p in json.loads(Path('captures/startup-v9-quotes.json').read_text())['pools'] if p['pool']=='0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca')
  config=int(json.loads(Path('reports/amm/delegated-hook-fee-fields.json').read_text())['original'],16)
  slots=json.loads(Path('reports/amm/delegated-hook-accounting.json').read_text())['slots']
  cls.kw=dict(v4_curve=load(seed['accounts']['0x8366a39cc670b4001a1121b8f6a443a643e40951']['storage'],c['key']),v4_key=c['key'],v3_curve=State.load(meta),pool_meta=meta,hook_config=config,hook_storage={k:int(v,16) for k,v in seed['accounts'][c['key']['hooks']]['storage'].items()},accounting_slots=slots,weth_balance=0,native_balance=0)
 def run_preview(self,kw):return preview(self.plan['actions'][0]['data'],self.plan['actions'][2]['data'],**kw)
 def test_join_matches_actual_validated_checkpoint_results(self):
  before=copy.deepcopy(self.kw);r=self.run_preview(self.kw)
  self.assertEqual(self.kw,before)
  expected=json.loads(Path('reports/amm/delegated-settler-chain-preview.json').read_text())
  self.assertEqual(r['v3_fill'],expected['v3_fill']);self.assertEqual(r['hook_fee']['net'],expected['v4_net'])
  self.assertEqual(r['weth_balance'],1);self.assertEqual(r['native_balance'],0)
 def test_downstream_failure_leaves_every_input_unchanged(self):
  kw=copy.deepcopy(self.kw);kw['v3_curve'].bitmap={};before=copy.deepcopy(kw)
  with self.assertRaisesRegex(ValueError,'unknown bitmap'):self.run_preview(kw)
  self.assertEqual(kw,before)
 def test_inventory_carried_to_second_preview(self):
  first=self.run_preview(self.kw);kw=dict(self.kw,**{k:first[k] for k in ('v4_curve','v3_curve','hook_storage','weth_balance','native_balance')});second=self.run_preview(kw)
  self.assertEqual(second['v3_intent']['amount'],second['hook_fee']['net'])
  self.assertEqual(second['weth_balance'],1)
  for slot in self.kw['accounting_slots'].values():self.assertGreater(second['hook_storage'][slot],first['hook_storage'][slot])
