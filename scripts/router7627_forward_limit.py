"""Observed forward optimizer for a single interval only; no crossing solver."""
from math import isqrt
from v3_state import Q96
from router7627_reverse_limit import _empty_interval

def limit(v3,v4):
 if (v3.fee,v3.spacing,v4.spacing)!=(100,1,1):raise ValueError('unverified optimizer profile')
 if min(v3.sqrt,v4.sqrt,v3.liquidity,v4.liquidity)<=0:raise ValueError('nonpositive optimizer state')
 factor3=999900;root=isqrt(factor3*999840)
 r4=v4.liquidity*v4.sqrt//Q96;r3=v3.liquidity*v3.sqrt//Q96
 candidate=((factor3*r4+1000000*r3)*Q96)//(factor3*v4.liquidity+root*v3.liquidity)
 target3=candidate*root//1000000
 if not candidate<v4.sqrt or not target3>v3.sqrt:raise ValueError('not forward optimizer branch')
 _empty_interval(v4,candidate);_empty_interval(v3,target3)
 return candidate
