import sys,tempfile,json,unittest
from pathlib import Path
from unittest.mock import patch,Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from checkpoint_recovery import RecoveryState,RecoveryRunner

class RecoveryTests(unittest.TestCase):
 def setUp(self):self.events=[];self.s=RecoveryState(self.events.append,max_blocks=4)
 def row(self,kind,**kwargs):self.s.observe(dict(kind=kind,mono_ns=len(self.events)+1,epoch=0,**kwargs))
 def connect(self):
  for stream in ('chain','nitro'):self.row('connected',stream=stream)
  for sub in ('logs','heads'):self.row('subscribed',subscription_kind=sub)
 def head(self,n,parent=None):self.row('head',payload=dict(number=hex(n),hash=f'h{n}',parentHash=parent or f'h{n-1}'))
 def nitro(self,n,seq=None):self.row('nitro_push',payload=dict(messages=[dict(sequenceNumber=seq if seq is not None else n,blockHash=f'h{n}')]))
 def seed(self,n=10):return dict(anchor_verified=True,failed=[],pools=[{}],accounts={'a':{}},anchor=dict(number=hex(n),hash=f'h{n}'))
 def ready(self):
  self.connect();self.head(10);self.nitro(10);self.s.accept(self.seed(),'checkpoint.json',0);self.head(11);self.nitro(11);self.assertTrue(self.s.align())
 def test_requires_both_subscriptions_and_push_overlap(self):
  self.connect();self.head(10);self.nitro(10);self.s.accept(self.seed(),'x',0)
  self.assertFalse(self.s.align());self.head(11);self.assertFalse(self.s.align());self.nitro(11);self.assertTrue(self.s.align())
  self.assertTrue(self.s.status()['replay_ready']);self.assertFalse(self.s.status()['decision_ready']);self.assertFalse(self.s.status()['state_valid'])
 def test_chain_gap_closes_segment_immediately(self):
  self.ready();self.row('gap',stream='chain');self.assertIsNone(self.s.ready);self.assertIsNotNone(self.s.intervals[0]['end_mono_ns']);self.assertFalse(self.s.streams_ready())
 def test_binance_redundant_link_does_not_reset_pool(self):
  self.ready();self.row('gap',stream='binance');self.assertIsNotNone(self.s.ready);self.assertEqual(self.s.generation,0)
 def test_inflight_snapshot_discarded_after_gap(self):
  self.connect();self.head(10);self.nitro(10);self.row('gap',stream='nitro')
  self.assertFalse(self.s.accept(self.seed(),'old',0));self.assertIsNone(self.s.candidate)
 def test_nitro_sequence_gap_invalidates(self):
  self.ready();self.nitro(13);self.assertIsNone(self.s.ready);self.assertEqual(self.s.reason,'nitro_sequence_gap')
 def test_duplicate_sequence_is_harmless_but_conflict_invalidates(self):
  self.ready();self.nitro(11);self.assertIsNotNone(self.s.ready);self.nitro(12,seq=11);self.assertIsNone(self.s.ready)
 def test_head_parent_conflict_invalidates(self):
  self.ready();self.head(12,'wrong');self.nitro(12);self.assertIsNone(self.s.ready);self.assertEqual(self.s.reason,'canonical_head_discontinuity')
 def test_removed_log_invalidates(self):
  self.ready();self.row('chain_log',payload={'removed':True});self.assertIsNone(self.s.ready)
 def test_anchor_hash_mismatch_never_promotes(self):
  self.connect();self.head(10);self.nitro(10);s=self.seed();s['anchor']['hash']='other';self.s.accept(s,'x',0)
  with self.assertRaises(ValueError):self.s.align()
 def test_failed_snapshot_never_promotes(self):
  s=self.seed();s['failed']=[{'pool':'x'}]
  with self.assertRaises(ValueError):self.s.accept(s,'x',0)
 def test_reconnect_requires_fresh_generation_and_subscriptions(self):
  self.ready();self.row('gap',stream='chain');self.s.observe(dict(kind='connected',stream='chain',epoch=1,mono_ns=100));self.assertFalse(self.s.streams_ready());self.assertFalse(self.s.accept(self.seed(),'stale',0))
 def test_transient_retry_budget_recovers_after_cooldown_and_stability(self):
  with tempfile.TemporaryDirectory()as d:
   cfg=Path(d)/'config.json';cfg.write_text('{"pools":[{}]}')
   opts=dict(max_buffer_blocks=4,max_attempts=1,retry_seconds=1,retry_max_seconds=2,bootstrap_timeout_seconds=10,alignment_timeout_seconds=10,rpc='unused',stable_stream_seconds=5)
   runner=RecoveryRunner(d,cfg,opts,self.events.append,[]);runner.attempts=1;runner.state=self.s;self.connect();self.head(10);self.nitro(10);runner.fail('generation_changed_during_snapshot',0)
   with patch('checkpoint_recovery.subprocess.Popen')as spawn:
    runner.poll(now=.5);spawn.assert_not_called()
    self.s.last_mono=6_000_000_000
    runner.poll(now=3);spawn.assert_called_once();self.assertEqual(runner.attempts,1);self.assertFalse(runner.status()['decision_ready'])
    runner.close()
 def test_interleaved_rpc_forks_follow_nitro_without_reset(self):
  self.connect()
  for r in json.loads((Path(__file__).parent/'fixtures/checkpoint-fork.json').read_text()):self.s.observe(r)
  self.assertEqual(self.s.generation,0)
  self.assertGreater(self.s.confirmed_count,20)
 def test_rpc_fork_before_and_after_nitro_is_harmless(self):
  self.ready();generation=self.s.generation
  self.row('head',payload=dict(number='0xc',hash='fork12',parentHash='h11'))
  self.nitro(12);self.head(12)
  self.row('head',payload=dict(number='0xc',hash='fork12',parentHash='h11'))
  self.assertEqual(self.s.generation,generation);self.assertEqual(self.s.last_head,(12,'h12'))
 def test_missing_canonical_head_times_out(self):
  self.ready();self.nitro(12)
  self.s.observe(dict(kind='coverage',mono_ns=20_000_000_000))
  self.assertEqual(self.s.reason,'canonical_head_timeout');self.assertIsNone(self.s.ready)
 def test_out_of_order_canonical_heads_wait_for_missing_parent(self):
  self.ready();self.nitro(12);self.nitro(13);self.head(13)
  self.assertEqual(self.s.last_head,(11,'h11'));self.head(12)
  self.assertEqual(self.s.last_head,(13,'h13'));self.assertEqual(self.s.generation,0)

if __name__=='__main__':unittest.main()
