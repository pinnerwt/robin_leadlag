"""Observed single-interval reverse optimizer, not a general crossing solver.

Router optimizer uses 100ppm V3 and conservative 160ppm V4 factors even when
actual V4 hook returns 40ppm. Reserve intermediates are floored separately.
"""
from math import isqrt
from v3_state import tick_sqrt,sqrt_tick,Q96

def _empty_interval(state,target):
 lo,hi=sorted((state.tick,tick_sqrt(target)))
 for tick in range(lo,hi+1):
  word=tick>>8
  if word not in state.bitmap:raise ValueError('missing optimizer bitmap')
  if min(state.sqrt,target)<=sqrt_tick(tick)<=max(state.sqrt,target) and state.bitmap[word]&(1<<(tick&255)):raise ValueError('optimizer requires initialized-tick crossing solver')

def limit(v3,v4):
 if (v3.fee,v3.spacing,v4.spacing)!=(100,1,1):raise ValueError('unverified optimizer profile')
 if min(v3.sqrt,v4.sqrt,v3.liquidity,v4.liquidity)<=0:raise ValueError('nonpositive optimizer state')
 factor3=999900;factor4=999840;root=isqrt(factor3*factor4)
 reserves3=v3.liquidity*v3.sqrt//Q96;reserves4=v4.liquidity*v4.sqrt//Q96
 numerator=(factor4*reserves3+1000000*reserves4)*Q96
 denominator=factor4*v3.liquidity+root*v4.liquidity
 candidate=numerator//denominator;target4=candidate*root//1000000
 if not candidate<v3.sqrt or not target4>v4.sqrt:raise ValueError('not reverse optimizer branch')
 _empty_interval(v3,candidate);_empty_interval(v4,target4)
 return candidate
