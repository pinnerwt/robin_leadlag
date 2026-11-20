import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path('scripts').resolve()))
from metric_strategy import *
from metric_strategy_replay import Scenario
class StrategyTest(unittest.TestCase):
 def setUp(self):
  self.p=Policy(D(500),D(10));self.inv=Inventory();self.bbo=dict(bid='100',ask='100',available_ns=0)
 def quote(self,q='5',ask='499',bid='501',t=0):return dict(status='priced',state_valid=True,size_tokens=q,ask_usdg=ask,bid_usdg=bid,available_ns=t,state_version='s1')
 def test_capacity_and_existing_inventory(self):
  self.assertEqual(quantities(self.p,self.inv,D(100),18)['buy'],D(5))
  self.assertEqual(quantities(self.p,Inventory(D(2),D(300)),D(100),18),dict(buy=D(3),sell=D(2)))
  self.assertEqual(quantities(self.p,Inventory(D(6),D(500)),D(100),18)['buy'],0)
 def test_threshold_sweep_uses_same_size_quote(self):
  outcomes=[decide(Policy(D(500),D(y)),self.inv,'buy',D(5),self.quote(),self.bbo,0) is not None for y in (10,15,20,25,30)]
  self.assertEqual(outcomes,[True,True,True,False,False])
 def test_delayed_requote_and_invalid_state(self):
  order=decide(self.p,self.inv,'buy',D(5),self.quote(),self.bbo,0)
  self.assertIsNone(fill(self.p,self.inv,order,self.quote(),self.bbo,149_000_000))
  self.assertIsNone(fill(self.p,self.inv,order,self.quote(ask='500'),self.bbo,150_000_000))
  self.assertIsNone(decide(self.p,self.inv,'sell',D(5),self.quote(),self.bbo,0))
  self.assertIsNone(decide(self.p,self.inv,'buy',D(5),dict(self.quote(),state_valid=False),self.bbo,0))
 def test_replay_same_policy_no_fixed_exit(self):
  s=Scenario(self.p);event=dict(available_ns=0,token='t',pool='p',base_decimals=18,bbo=self.bbo,state_valid=True)
  quoter=lambda pool,q,t:self.quote(q=str(q),t=t)
  s.step(event,quoter,lambda *args:True);s.step(dict(event,available_ns=150_000_000),quoter,lambda *args:True)
  self.assertEqual(s.positions['t'],Inventory(D(5),D(1)));self.assertEqual(len(s.fills),1)
  # Inventory is shared across pools for the same token.
  s.step(dict(event,available_ns=151_000_000,pool='p2'),quoter,lambda *args:True)
  s.step(dict(event,available_ns=301_000_000,pool='p2'),quoter,lambda *args:True)
  self.assertEqual(s.positions['t'],Inventory(D(0),D(502)));self.assertEqual(len(s.fills),2)
 def test_stale_bbo_and_future_quote(self):
  self.assertIsNone(decide(self.p,self.inv,'buy',D(5),self.quote(),self.bbo,1_000_000_001))
  self.assertIsNone(decide(self.p,self.inv,'buy',D(5),self.quote(t=1),self.bbo,0))
if __name__=='__main__':unittest.main()

class RejectedCommitTest(unittest.TestCase):
 def test_failed_state_commit_never_books_fill(self):
  p=Policy(D(500),D(10));s=Scenario(p)
  e=dict(available_ns=0,token='t',pool='p',base_decimals=18,bbo=dict(bid='100',ask='100',available_ns=0),state_valid=True)
  quote=lambda pool,q,t:dict(status='priced',state_valid=True,size_tokens=str(q),bid_usdg='501',ask_usdg='499',available_ns=t,state_version='s')
  s.step(e,quote,lambda *args:False);s.step(dict(e,available_ns=150_000_000),quote,lambda *args:False)
  self.assertEqual(s.positions['t'],Inventory());self.assertEqual(s.fills,[]);self.assertEqual(s.cancelled,1)

class OneSidedQuoteTest(unittest.TestCase):
 def test_ask_revert_does_not_hide_executable_bid(self):
  p=Policy(D(1000),D(10));inv=Inventory(D(5),D(500));bbo=dict(bid='100',ask='100',available_ns=0)
  q=dict(status='partial',state_valid=True,size_tokens='5',bid_usdg='501',ask_usdg=None,available_ns=0)
  self.assertIsNotNone(decide(p,inv,'sell',D(5),q,bbo,0))
  self.assertIsNone(decide(p,inv,'buy',D(5),q,bbo,0))
  q.update(bid_usdg=None,ask_usdg='499')
  self.assertIsNotNone(decide(p,inv,'buy',D(5),q,bbo,0))
  self.assertIsNone(decide(p,inv,'sell',D(5),q,bbo,0))
