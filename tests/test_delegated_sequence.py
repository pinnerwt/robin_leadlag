import json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from delegated_compressed import inspect
from delegated_sequence import preview,StrategyReverted
class SequenceTest(unittest.TestCase):
 def test_original_callback_outcomes_and_fresh_reads(self):
  calldata=json.loads(Path('reports/amm/delegated-router-funded-balance-0.json').read_text())['tx']['data'];plan=inspect(calldata)
  initial={(r['target'],r['calldata']):r['value'].to_bytes(32,'big') for g in plan['condition_groups'] for r in g['records']}
  for file in ('probe','fresh-price'):
   cases=json.loads(Path('reports/amm/delegated-continuation-'+file+'.json').read_text())['cases']
   for case in cases:
    attempts=[]
    def execute(state,strategy,index):
     attempts.append(index);state['writes']=state.get('writes',0)+1
     if case['outcomes'][index] is None:raise StrategyReverted()
     if index==0 and case.get('second_price_shift_bps') is not None:
      r=plan['condition_groups'][0]['records'][-1];state[(r['target'],r['calldata'])]=(r['value']*(10000+case['second_price_shift_bps'])//10000).to_bytes(32,'big')
    if all(v is None for v in case['outcomes']):
     with self.assertRaises(StrategyReverted):preview(calldata,initial,read=lambda s,r:s[(r['target'],r['calldata'])],execute=execute)
    else:
     result=preview(calldata,initial,read=lambda s,r:s[(r['target'],r['calldata'])],execute=execute)
     returned=bytes.fromhex(case['callback_returns'][0]['output'][2:])
     self.assertEqual(result['success_mask'],int.from_bytes(returned[64:96],'big'))
     self.assertEqual(result['state']['writes'],result['success_mask'].bit_count())
    self.assertEqual(attempts,case['attempted']);self.assertNotIn('writes',initial)
 def test_unknown_dependency_is_not_treated_as_strategy_revert(self):
  calldata=json.loads(Path('reports/amm/delegated-router-funded-balance-0.json').read_text())['tx']['data']
  with self.assertRaises(KeyError):preview(calldata,{},read=lambda s,r:s[r['target']],execute=lambda *args:None)
