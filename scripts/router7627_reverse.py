"""Observed reverse first leg; limit must be computed from local state separately."""
from router7627_second_leg import ROUTER,POOL
from v3_state import MIN_SQRT

def first_leg(limit):
 if type(limit) is not int or not MIN_SQRT<limit<1<<160:raise ValueError('invalid reverse limit')
 values=[int(ROUTER,16),1,10**19,limit,160,0]
 return dict(pool=POOL,zero=True,amount=10**19,limit=limit,data='0x128acb08'+b''.join(v.to_bytes(32,'big') for v in values).hex(),execution_complete=False)


def second_leg(amount0,amount1):
 """Observed V3 callback deltas feed native/USDG V4 exact input.

 Research profile only: does not compute the first leg's optimized limit or
 execute V4 hooks. Amounts must come from local V3 state, never swap logs.
 """
 from router7627_credit import MANAGER,USDG
 from router7627_second_leg import LIMIT
 if any(type(x) is not int or not -(1<<255)<=x<(1<<255) for x in (amount0,amount1)) or amount0<=0 or amount1>=0:
  raise ValueError('unverified reverse callback direction')
 hook=int('987e330f00b79864a07fe81dfac344d0078abcc0',16)
 words=[0,int(USDG,16),0x800000,1,hook,0,amount1%(1<<256),LIMIT,288,0]
 return dict(to=MANAGER,data='0xf3cd914c'+b''.join(v.to_bytes(32,'big') for v in words).hex(),native_owed=amount0,usdg_input=-amount1,execution_complete=False)
