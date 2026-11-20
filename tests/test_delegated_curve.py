"""Recorded-bytecode curve parity with explicit synthetic observations."""
import json
from pathlib import Path
import sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from v3_state import State,MIN_SQRT

class DelegatedCurveTest(unittest.TestCase):
 def test_two_pool_quote_and_bytecode_transfer(self):
  up=json.loads(Path('reports/amm/delegated-upstream-curve-probe.json').read_text())
  down=json.loads(Path('reports/amm/delegated-two-pool-curve-probe.json').read_text())
  quotes=json.loads(Path('captures/startup-v9-quotes.json').read_text())
  self.assertEqual(up['anchor'],down['anchor']);self.assertEqual(up['anchor'],quotes['anchor']['hash'])
  u=State.load(up['state']);first=u.swap(True,266955244349511648,MIN_SQRT+1)
  self.assertEqual(first,up['expected']);self.assertEqual(down['input_amount'],-first['amount1'])
  pool='0xc61284332117c3fb23a2a56cceffd07f7af60029'
  d=State.load(next(p for p in quotes['pools'] if p['pool']==pool))
  self.assertEqual(d.swap(True,down['input_amount'],MIN_SQRT+1),down['expected'])
  for case,address in [(up,'0xc3c9f0171490ef0f4536fe493f3b0ebb5ee0cb5e'),(down,pool)]:
   r=case['result'];self.assertIsNone(r['error']);self.assertEqual(len(r['calls']),1)
   self.assertTrue(r['calls'][0]['data'].startswith('0xa9059cbb'))
   self.assertEqual(int(r['calls'][0]['data'][-64:],16),-case['expected']['amount1'])
   writes=[w for w in r['storage_writes'] if w['address']==address and int(w['slot'],16)==0]
   self.assertEqual(int(writes[-1]['value'],16)&((1<<160)-1),case['expected']['sqrt'])
