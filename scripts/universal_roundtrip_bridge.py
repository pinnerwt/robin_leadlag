"""Atomic local wrap/V3/V4/V3/unwrap transitions; native callback not modeled."""
import copy
from universal_roundtrip import plan
from v4_v3_bridge import Bridge as Base,pool_key,WETH

class Bridge(Base):
 def apply(self,calldata,sender,native_value):
  if not self.valid:raise ValueError('bridge invalid: '+self.reason)
  route=plan(calldata);op=route['v4'];usd=op['currency1']
  if pool_key(op)!=self.key:raise ValueError('unknown V4 pool')
  if self.flags.get(sender.lower()) is not True:raise ValueError('unknown or non-exempt hook flag')
  if native_value!=route['wrap_amount']:raise ValueError('native funding mode not verified')
  if usd not in self.inventory or WETH not in self.inventory:raise ValueError('missing router inventory')
  matches=[a for a,p in self.meta.items() if p['fee']==route['v3_fee'] and set(p['tokens'])=={usd,WETH}]
  if len(matches)!=1:raise ValueError('missing or ambiguous V3 pool')
  pool=matches[0];v3=copy.deepcopy(self.states[pool]);v4=copy.deepcopy(self.v4);inv=dict(self.inventory)
  inv[WETH]+=route['wrap_amount']
  if inv[WETH]>=1<<255:raise ValueError('WETH amount overflow')
  zero=self.meta[pool]['tokens'][0]==WETH
  first=v3.swap(zero,inv[WETH],None,True)
  spent=first['amount0'] if zero else first['amount1'];received=-first['amount1'] if zero else -first['amount0']
  if not 0<=spent<=inv[WETH] or received<0:raise ValueError('invalid first V3 flow')
  inv[WETH]-=spent;inv[usd]+=received
  middle=v4.swap(False,-op['amount'],op['limit'],True)
  usd_spent=middle['amount1'];token_delivered=-middle['amount0']
  if not 0<=usd_spent<=inv[usd] or token_delivered<0:raise ValueError('insufficient USDG for V4')
  inv[usd]-=usd_spent
  if not 0<inv[usd]<1<<255:raise ValueError('invalid final V3 input')
  final_requested=inv[usd]
  # Reuse the candidate already changed by the first leg, never the old snapshot.
  last=v3.swap(not zero,final_requested,None,True)
  spent=last['amount1'] if zero else last['amount0'];received=-last['amount0'] if zero else -last['amount1']
  if not 0<=spent<=inv[usd] or received<0:raise ValueError('invalid final V3 flow')
  inv[usd]-=spent;inv[WETH]+=received
  if inv[WETH]>=1<<256:raise ValueError('WETH inventory overflow')
  unwrapped=inv[WETH];inv[WETH]=0
  self.states[pool]=v3;self.v4=v4;self.inventory=inv
  return dict(pool=pool,first_v3=first,v4=middle,last_v3=last,final_requested=final_requested,
              token_delivered=token_delivered,unwrapped=unwrapped,state_complete=False,
              transaction_success_assumed=True,partial_reason='native recipient execution not modeled')
