import json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from c9_balance_route import allocation_transition
from hub_state import MASK248
class C7SettlementTest(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.cases=json.loads(Path('tests/fixtures/c7_settlement.json').read_text())
  cls.pools=json.loads(Path('tests/fixtures/c9_balance_route.json').read_text())['pools']
 def test_four_successful_bytecode_allocation_results(self):
  for c in self.cases:
   result=allocation_transition(c['calldata'],int(c['old_in']),int(c['old_out']),0,self.pools)
   self.assertEqual(result['allocation_in'],int(c['new_in']))
   self.assertEqual(result['allocation_out'],int(c['new_out']))
   self.assertEqual(result['operations'][0]['amount'],result['quote']['amount_out'])
 def test_unrecorded_callback_still_updates_aqua(self):
  c=self.cases[0]
  result=allocation_transition(c['calldata'],int(c['old_in']),int(c['old_out']),0,{})
  self.assertEqual(result['operations'],[])
  self.assertEqual(result['allocation_in'],int(c['new_in']))
 def test_next_swap_uses_changed_allocations(self):
  c=self.cases[0];a=allocation_transition(c['calldata'],int(c['old_in']),int(c['old_out']),0,self.pools)
  b=allocation_transition(c['calldata'],a['allocation_in'],a['allocation_out'],0,self.pools)
  self.assertLess(b['quote']['amount_out'],a['quote']['amount_out'])
 def test_inactive_entry_rejected(self):
  c=self.cases[0]
  for flag in (0,255):
   for side in ('in','out'):
    values={s:int(c['old_'+s]) for s in ('in','out')}
    values[side]=(flag<<248)|(values[side]&MASK248)
    with self.assertRaises(ValueError):allocation_transition(c['calldata'],values['in'],values['out'],0,self.pools)
if __name__=='__main__':unittest.main()
