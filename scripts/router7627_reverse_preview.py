"""Pure local reverse-route math for the verified 100/40-ppm fee profile.

Caller may supply the router's V3 limit or use None for the verified
single-interval optimizer, plus independently established
hook fee. This does not solve tick-crossing optimization, update hook state, or certify a
transaction. Input states are not mutated; output is tentative until accepted.
"""
from router7627_reverse import first_leg,second_leg
from router7627_second_leg import LIMIT
from router7627_profit import required_balance

def preview(v3,v4,limit,parameter):
 if (v3.fee,v3.spacing,v4.fee,v4.spacing)!=(100,1,40,1):raise ValueError('unverified fee/spacing profile')
 if limit is None:
  from router7627_reverse_limit import limit as optimized_limit
  limit=optimized_limit(v3,v4)
 leg=first_leg(limit)
 a=v3.swap(True,leg['amount'],limit)
 intent=second_leg(a['amount0'],a['amount1'])
 b=v4.swap(False,intent['usdg_input'],LIMIT)
 if b['unfilled']:raise ValueError('unverified partially filled V4 second leg')
 if b['amount1']!=intent['usdg_input']:raise ValueError('V4 input mismatch')
 owed=a['amount0'];received=-b['amount0'];profit=received-owed
 minimum=required_balance(0,0,parameter)['minimum']
 return dict(v3=a,v4=b,v3_calldata=leg['data'],v4_calldata=intent['data'],native_owed=owed,native_received=received,gross_native_profit=profit,minimum_native_profit=minimum,profit_gate_passed=profit>=minimum,execution_complete=False)
