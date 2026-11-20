import copy,json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from aqua_book import make_book,C9,R777
from c9_balance_route import plan
from v3_state import sqrt_tick
class AquaBookTest(unittest.TestCase):
 def build(self):
  self.c7=json.loads(Path('tests/fixtures/c7_settlement.json').read_text())[0];r=plan(self.c7['calldata'])
  self.c777=json.loads(Path('tests/fixtures/router777_plan.json').read_text())[0]
  pool='0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca'
  seed=dict(complete=True,anchor=dict(hash='test'),pools=[dict(pool=pool,tokens=[r['token_out'],r['token_in']],fee=100,spacing=1,
     sqrt=str(sqrt_tick(-201180)),tick=-201180,liquidity=str(10**20),bitmap={str(i):0 for i in range(-800,-770)},ticks={})])
  seed['aqua']=dict(anchor_hash='test',strategies=[dict(maker=r['maker'],program=r['program'],balances={r['token_in']:self.c7['old_in'],r['token_out']:self.c7['old_out']})],router_inventory={r['token_out']:0})
  registry=dict(anchor_hash='test',routers={C9:dict(code_hash='pinned',implementation_code_hash='pinned'),R777:dict(code_hash='pinned')})
  registry['routers'][C9]['dependencies']=[dict(address=a,code_hash='pinned') for a in ('0x111111338c5091e8440b67b168bae16a668ac0de','0x1111113ccf1426a8e30e2bff5e005d929bf6a90a')]
  return seed,registry
 def test_routes_share_follower_book(self):
  seed,reg=self.build();b=make_book(seed,reg,True)
  self.assertIs(b.states,b.aqua.states)
  for n,target,data in [(1,C9,self.c7['calldata']),(2,R777,self.c777['calldata'])]:
   self.assertEqual(len(b.proposal(dict(tx=str(n),to=target,data=data))),1)
  self.assertEqual(b.counts['decoded_transactions'],2)
 def test_unknown_transaction_blocks_later_aqua_use(self):
  seed,reg=self.build();b=make_book(seed,reg,True)
  b.proposal(dict(tx='unknown',to='0x'+'99'*20,data='0x12345678'))
  before=copy.deepcopy((b.states,b.aqua.allocations))
  self.assertEqual(b.proposal(dict(tx='next',to=C9,data=self.c7['calldata'])),[])
  self.assertEqual((b.states,b.aqua.allocations),before)
  self.assertIn('next',b.unsupported)
 def test_anchor_and_pin_required(self):
  seed,reg=self.build();seed['aqua']['anchor_hash']='other'
  with self.assertRaises(ValueError):make_book(seed,reg,True)
  seed['aqua']['anchor_hash']='test';reg['routers'][R777]={}
  with self.assertRaises(ValueError):make_book(seed,reg,True)
if __name__=='__main__':unittest.main()
