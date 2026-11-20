import copy,json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from delegated_local import preview
from delegated_sequence import StrategyReverted
from v3_state import State
class LocalTest(unittest.TestCase):
 def setUp(self):
  self.input=json.loads(Path('reports/amm/delegated-local-input.json').read_text())
  self.state={**self.input['state'],'curves':{a:State.load(v) for a,v in self.input['state']['curves'].items()}}
 def test_original_conditions_match_actual_callback(self):
  evidence=json.loads(Path('reports/amm/delegated-condition-checkpoint-probe.json').read_text())['cases'][0]['result']
  self.assertIsNone(evidence['error']);self.assertEqual(evidence['calls'],[])
  self.assertFalse(any(c['data'].startswith('0x273a5b72') for c in evidence['execution_calls']))
  with self.assertRaises(StrategyReverted):preview(self.input['calldata'],self.state)
 def test_sequential_state_and_real_manager_results(self):
  before=copy.deepcopy(self.state);relaxed=json.loads(Path('reports/amm/delegated-local-relaxed-preview.json').read_text())
  actual=preview(relaxed['calldata'],self.state)
  self.assertEqual(actual['attempted'],[0,1]);self.assertEqual(actual['success_mask'],3)
  evidence=json.loads(Path('reports/amm/delegated-v4-sequence-probe.json').read_text())
  self.assertEqual([e['hook_fee'] for e in actual['state']['executed']],evidence['fees'])
  returns=[r for r in evidence['result']['execution_returns'] if r['selector']=='0xf3cd914c' and r['result']=='Return']
  for e,r in zip(actual['state']['executed'],returns):self.assertEqual(e['output_native'],int(r['output'],16)>>128)
  self.assertEqual(self.state,before);self.assertFalse(actual['execution_complete'])
