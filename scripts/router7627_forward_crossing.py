"""Research optimizer: V3 crossings and uninitialized V4 word boundaries.

Does not certify input checkpoint consistency or execute swaps/hook transitions.
Returns candidate limit, not realized amount. Unknown state fails explicitly.
"""
import copy
from math import isqrt
from v3_state import Q96,sqrt_tick,ceil

def optimize(v3,v4,max_steps=128):
 if (v3.fee,v3.spacing,v4.spacing)!=(100,1,1):raise ValueError('unverified optimizer profile')
 if type(max_steps) is not int or max_steps<=0:raise ValueError('invalid iteration bound')
 a,b=copy.deepcopy(v3),copy.deepcopy(v4);root=isqrt(999900*999840);iterations=[];inverse3=(1<<192)//a.sqrt
 for _ in range(max_steps):
  if min(a.sqrt,b.sqrt,a.liquidity,b.liquidity)<=0:raise ValueError('nonpositive optimizer state')
  candidate=((999900*(b.liquidity*b.sqrt//Q96)+1000000*((a.liquidity*Q96)//inverse3))*Q96)//(999900*b.liquidity+root*a.liquidity)
  target=candidate*root//1000000
  if not candidate<b.sqrt or not target>a.sqrt:raise ValueError('not forward optimizer branch')
  tick4,initialized4=b.next_tick(b.tick,True);boundary4=sqrt_tick(tick4)
  tick3,initialized=a.next_tick(a.tick,False);boundary=sqrt_tick(tick3)
  entry=dict(candidate=candidate,v3_sqrt=a.sqrt,v3_liquidity=a.liquidity,v4_sqrt=b.sqrt,next_v3_tick=tick3)
  iterations.append(entry)
  if target<boundary and candidate>boundary4:return dict(limit=candidate,iterations=iterations,execution_complete=False)
  inv0=inverse3;inv1=(1<<192)//boundary
  net=ceil(a.liquidity*Q96,inv1)-ceil(a.liquidity*Q96,inv0)
  gross=ceil(net*1000000,999900)
  available=b.liquidity*(b.sqrt-boundary4)//Q96
  if candidate<=boundary4 and (target<boundary or available<gross):
   if initialized4:raise ValueError('initialized V4 crossing solver required')
   effective=available*999900//1000000
   reserve3=ceil(a.liquidity*Q96,inverse3)+effective
   inverse3=ceil(a.liquidity*Q96,reserve3)
   a.sqrt=(1<<192)//inverse3
   b.sqrt=boundary4;b.tick=tick4-1
   entry.update(v4_boundary=tick4,v4_output=available,v3_effective_input=effective)
   continue
  remaining=ceil(b.liquidity*b.sqrt,Q96)-gross
  if remaining<=0:raise ValueError('optimizer reserve exhausted')
  b.sqrt=remaining*Q96//b.liquidity
  entry.update(usdg_net=net,usdg_gross=gross)
  if initialized:
   if tick3 not in a.ticks:raise ValueError('unknown initialized V3 tick')
   a.liquidity+=a.ticks[tick3][1]
   if not 0<a.liquidity<1<<128:raise ValueError('optimizer liquidity bounds')
  a.sqrt=boundary;a.tick=tick3;inverse3=inv1
 raise ValueError('optimizer iteration bound exceeded')
