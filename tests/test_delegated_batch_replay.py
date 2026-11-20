import copy,json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path('scripts').resolve()))
from delegated_batch_replay import BatchReplay
class BatchReplayTest(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.seed=json.loads(Path('captures/startup-v9-dependencies.json').read_text());cls.quotes=json.loads(Path('captures/startup-v9-quotes.json').read_text())
  cls.tx=next(t for t in map(json.loads,Path('reports/amm/delegated-router-txs.jsonl').read_text().splitlines()) if t['tx'].startswith('0x99fa4228'))
  cls.inventory=dict(anchor=cls.seed['anchor']['hash'],weth_balance=0,native_balance=0,usdg_balance=0)
 def make(self,assume_success=True):return BatchReplay(self.seed,self.quotes,self.tx['data'],inventory=self.inventory,transaction_target=self.tx['to'],last_ordinal=-1,assume_success=assume_success)
 def test_atomic_commit_duplicate_and_private_result(self):
  r=self.make();out=r.apply(self.tx,0);snapshot=r.snapshot();again=r.apply(copy.deepcopy(self.tx),0)
  self.assertEqual(r.snapshot(),snapshot);self.assertEqual(out,again);self.assertFalse(out['complete_scope_verified'])
  out['v3_curve'].sqrt=1;self.assertEqual(r.snapshot(),snapshot)
  # Explicit synthetic second event: order validity is not established by replay.
  next_tx=dict(self.tx,tx='synthetic-second-event');second=r.apply(next_tx,1)
  self.assertEqual(second['v3_intent']['amount'],second['hook_fee']['net'])
  self.assertEqual(r.last_ordinal,1)
 def test_gap_blocks_further_updates(self):
  r=self.make();before=r.snapshot()
  with self.assertRaisesRegex(ValueError,'gap'):r.apply(self.tx,1)
  with self.assertRaisesRegex(ValueError,'replay invalid'):r.apply(self.tx,0)
  self.assertEqual(r.snapshot(),before)
 def test_unrelated_type4_invalidates_pins(self):
  r=self.make();before=r.snapshot()
  with self.assertRaisesRegex(ValueError,'delegation'):r.apply(dict(self.tx,to='0x'+'11'*20,raw_transaction='0x04'),0)
  self.assertEqual(r.snapshot(),before)
 def test_unknown_and_missing_envelope_invalidate(self):
  for patch in (dict(to='0x'+'11'*20),dict(raw_transaction=None)):
   r=self.make();before=r.snapshot()
   with self.assertRaises(ValueError):r.apply(dict(self.tx,**patch),0)
   self.assertIsNotNone(r.invalid_reason);self.assertEqual(r.snapshot(),before)
 def test_known_failure_preserves_state(self):
  r=self.make(False);before=r.snapshot()
  with self.assertRaisesRegex(ValueError,'minimum output'):r.apply(self.tx,0)
  self.assertEqual(r.snapshot(),before);self.assertEqual(r.last_ordinal,-1)
 def test_conflicting_duplicate_invalidates(self):
  r=self.make();r.apply(self.tx,0);before=r.snapshot()
  with self.assertRaisesRegex(ValueError,'conflict'):r.apply(dict(self.tx,tx='conflicting-id'),0)
  self.assertEqual(r.snapshot(),before)
 def test_transport_gap_stays_invalid(self):
  r=self.make();r.invalidate('websocket disconnected');before=r.snapshot()
  with self.assertRaisesRegex(ValueError,'websocket disconnected'):r.apply(self.tx,0)
  self.assertEqual(r.snapshot(),before)
