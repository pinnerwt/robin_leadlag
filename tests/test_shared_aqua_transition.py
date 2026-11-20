import json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from router777_plan import allocation_candidate
class SharedAquaTest(unittest.TestCase):
 def test_both_settlement_directions(self):
  f=json.loads(Path('tests/fixtures/router777_allocations.json').read_text())
  for c in f['cases']:
   r=allocation_candidate(c['calldata'],int(c['packed_in']),int(c['packed_out']),f['pools'])
   self.assertEqual(r['allocation_in'],int(c['allocation_in']))
   self.assertEqual(r['allocation_out'],int(c['allocation_out']))
   self.assertEqual(r['operation']['amount'],r['quote']['amount_out'])
if __name__=='__main__':unittest.main()
