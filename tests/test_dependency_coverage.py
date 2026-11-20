import json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from dependency_coverage import select_blocks
class DependencyCoverage(unittest.TestCase):
 def row(self,seq,caller,selector='0x12345678'):
  return json.dumps(dict(kind='feed_tx',sequence=seq,to='router',**{'from':caller},data=selector+'00'))
 def test_rare_older_route_selected_over_repeated_newest(self):
  r=select_blocks([self.row(8,'a'),self.row(8,'b'),self.row(9,'a'),self.row(10,'a')],10,1,5)
  self.assertEqual(r['selected_blocks'],[8]);self.assertEqual(r['covered_routes'],2);self.assertFalse(r['execution_state_complete'])
 def test_causal_window_gaps_and_selector_separation(self):
  r=select_blocks([self.row(1,'old'),self.row(9,'a'),self.row(10,'a','0xdeadbeef'),self.row(11,'future')],10,1,3)
  self.assertEqual(r['selected_blocks'],[10]);self.assertEqual(r['observed_routes'],3);self.assertEqual(r['eligible_routes'],2);self.assertEqual(len(r['uncovered_eligible_routes']),1);self.assertEqual(len(r['outside_window_routes']),1);self.assertFalse(r['observed_route_coverage_complete'])
 def test_empty_or_invalid_budget(self):
  self.assertEqual(select_blocks([],10)['selected_blocks'],[])
  with self.assertRaises(ValueError):select_blocks([],10,0)
