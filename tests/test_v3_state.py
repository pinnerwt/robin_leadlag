import copy,json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from v3_state import *
from v3_calldata import decode
class V3Tests(unittest.TestCase):
 def test_tick_roundtrip_and_edges(self):
  self.assertEqual(sqrt_tick(MIN_TICK),MIN_SQRT)
  self.assertEqual(sqrt_tick(MAX_TICK),MAX_SQRT)
  for t in [-887271,-100,-1,0,1,100,887271]:self.assertEqual(tick_sqrt(sqrt_tick(t)),t)
 def state(self):
  s=State(Q96,0,0,500,1,{w:0 for w in range(-4,4)},{})
  s.modify(-100,100,10**18);return s
 def test_lp_add_remove_and_unknown_atomicity(self):
  s=self.state();before=copy.deepcopy(s)
  with self.assertRaises(ValueError):s.modify(-100,2000,100)
  self.assertEqual(s,before)
  s.modify(-100,100,-10**18);self.assertEqual(s.liquidity,0);self.assertFalse(s.ticks);self.assertTrue(all(v==0 for v in s.bitmap.values()))
 def test_swap_exact_output_and_no_quote_mutation(self):
  s=self.state();before=copy.deepcopy(s)
  sell=s.swap(True,10**12);buy=s.swap(True,-(-sell['amount1']))
  self.assertEqual(s,before);self.assertEqual(buy['amount1'],sell['amount1']);self.assertLessEqual(buy['amount0'],sell['amount0'])
  s.swap(True,10**12,commit=True);self.assertLess(s.sqrt,Q96)
 def test_negative_tick_bitmap_and_missing_word(self):
  s=self.state();self.assertEqual(s.next_tick(-1,True),(-100,True))
  with self.assertRaises(ValueError):s.next_tick(-2000,True)
 def test_direct_swap_decode_and_unknown_router(self):
  a='0x'+'11'*20;pools={a:{'tokens':[a,'0x'+'22'*20],'fee':500}}
  word=lambda v:(v%(1<<256)).to_bytes(32,'big')
  raw=bytes.fromhex('128acb08')+word(0)+word(1)+word(-100)+word(MIN_SQRT+1)+word(160)+word(0)
  op=decode(a,raw,pools,set())[0];self.assertEqual(op['amount'],-100);self.assertTrue(op['zero'])
  with self.assertRaises(ValueError):decode('0x'+'33'*20,raw,pools,set())
 def test_calldata_state_is_never_replaced_with_log_price(self):
  from amm_feed_state import Book,SWAP
  a='0x'+'11'*20;b='0x'+'22'*20;state=self.state()
  p=dict(pool=a,tokens=[a,b],fee=500,spacing=1,sqrt=str(state.sqrt),tick=state.tick,liquidity=str(state.liquidity),bitmap=state.bitmap,ticks=state.ticks,base_index=0,base_token=a,quote_token=b,decimals=[18,18])
  book=Book(dict(complete=True,pools=[p]));w=lambda v:(v%(1<<256)).to_bytes(32,'big')
  raw='0x128acb08'+b''.join(map(w,[0,1,10**12,MIN_SQRT+1,160,0])).hex()
  tx=dict(to=a,data=raw,tx='test',mono_ns=1,recv_ns=1)
  self.assertEqual(book.proposal(tx),[a]);computed=book.states[a].sqrt;expected=book.expected['test'][0][1]
  data='0x'+b''.join(w(expected[k]+(1 if k=='sqrt' else 0)) for k in ['amount0','amount1','sqrt','liquidity','tick']).hex()
  book.validate(dict(address=a,topics=[SWAP],transactionHash='test',data=data))
  self.assertIn(a,book.invalid);self.assertEqual(book.states[a].sqrt,computed)
  self.assertIn('reason',book.quotes(a,['0.1'],tx)[0])
 def test_pinned_mainnet_quoter_fixtures(self):
  fixture=Path(__file__).resolve().parents[1]/'captures/amm-checkpoint.json'
  if not fixture.exists():self.skipTest('optional pinned mainnet fixture absent')
  seed=json.loads(fixture.read_text());pools={p['pool']:p for p in seed['pools']}
  from decimal import Decimal
  for check in seed['checks']:
   p=pools[check['pool']];s=State.load(p);sell=check['side']=='bid';base=p['base_index'];amount=int(Decimal(check['size_tokens'])*10**p['decimals'][base]);zero=(base==0)==sell
   result=s.swap(zero,amount if sell else -amount)
   self.assertEqual(str(abs(result['amount'+str(1-base)])),check['remote_amount'])
if __name__=='__main__':unittest.main()
