"""Local quote-state previews of guarded SPCX and direct WETH/USDG cycles.

Assumes success and full output credit. Not full settlement/economic validation.
Other routes reject. All curves are copied; original state remains untouched.
"""
from copy import deepcopy
from routera3d_v4 import NATIVE,WETH,USDG,HOOK,POOL_ID
from routera3d_hook import reverse_update
from v3_state import MIN_SQRT,MAX_SQRT
UPSTREAM='0xc3c9f0171490ef0f4536fe493f3b0ebb5ee0cb5e'
RECORDED='0xc61284332117c3fb23a2a56cceffd07f7af60029'
DIRECT='0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca'
SPCX='0x4a0e65a3eccec6dbe60ae065f2e7bb85fae35eea'

def preview(strategy,curves,*,hook_state,hook_config,block):
 actions=strategy['actions']
 expected=[(4,WETH,1,NATIVE,WETH,NATIVE,NATIVE,0,0,NATIVE),
 (1,UPSTREAM,1,WETH,SPCX,WETH,SPCX,500,10,NATIVE),
 (1,RECORDED,1,SPCX,USDG,SPCX,USDG,500,10,NATIVE),
 (0,NATIVE,0,USDG,NATIVE,NATIVE,USDG,0x800000,1,HOOK)]
 fields=('kind','target','direction','token_in','token_out','currency0','currency1','fee','spacing','hook')
 direct=[expected[0],(1,DIRECT,1,WETH,USDG,WETH,USDG,100,1,NATIVE),expected[-1]]
 if len(actions)==3:expected=direct
 if len(actions)!=len(expected) or any(tuple(a[k] for k in fields)!=e or a['reserved'] for a,e in zip(actions,expected)):
  raise ValueError('unverified SPCX action profile')
 amount=strategy['input_amount']
 if type(amount) is not int or not 0<amount<1<<127:raise ValueError('cycle input bounds')
 working=deepcopy(curves);fills=[];initial=amount
 for action in actions[1:-1]:
  address=action['target'];curve=working[address]
  if curve.fee!=action['fee'] or curve.spacing!=action['spacing']:raise ValueError('V3 profile mismatch')
  fill=curve.swap(True,amount,MIN_SQRT+1,True)
  if fill['unfilled']:raise ValueError('partial cycle fill not verified')
  amount=-fill['amount1'];fills.append(dict(pool=address,**fill))
 curve=working[POOL_ID]
 if curve.spacing!=1:raise ValueError('V4 profile mismatch')
 change=reverse_update(hook_state,hook_config,curve.sqrt,block);curve.fee=change['fee']
 fill=curve.swap(False,amount,MAX_SQRT-1,True)
 if fill['unfilled']:raise ValueError('partial cycle fill not verified')
 fills.append(dict(pool=POOL_ID,**fill))
 return dict(curves=working,hook_state=change['after'],hook_fee=change['fee'],fills=fills,input_native=initial,
  output_native=-fill['amount0'],native_difference=-fill['amount0']-initial,transaction_success_assumed=True,execution_complete=False)
