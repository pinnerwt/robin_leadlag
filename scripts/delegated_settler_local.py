"""Atomic quote-state preview for the verified V4/native/WETH/V3 bridge.

Caller must establish code pins, hook no-referral native-output branch and
intervening full wrap/credit semantics. This is not a full router decoder:
authorization, trailing actions, token accounting and pool observations omitted.
All inputs are initialized locally; no I/O, hashing, RPC, or implicit zero state.
"""
from copy import deepcopy
from delegated_settler_v4 import first_swap,ZERO
from delegated_settler_v3 import intent
from delegated_hook_fee import accounting_update
WETH='0x0bd7d308f8e1639fab988df18a8011f41eacad73'
HOOK='0xe5e702641ea86f4ae6cc3cdaed2b886f976be044'

def preview(first_action,third_action,*,v4_curve,v4_key,v3_curve,pool_meta,
            hook_config,hook_storage,accounting_slots,weth_balance,native_balance):
 if any(type(v) is not int or not 0<=v<1<<256 for v in (weth_balance,native_balance)):
  raise ValueError('invalid bridge inventory')
 a=first_swap(first_action)
 actual=dict(currency0=a['currency0'],currency1=a['currency1'],fee=a['fee'],tick_spacing=a['spacing'],hooks=a['hook'])
 if actual!=v4_key or a['hook']!=HOOK or a['currency0']!=ZERO or a['zero'] or a['fee']!=0:
  raise ValueError('unverified V4 native output branch')
 if v4_curve.fee!=0 or v4_curve.spacing!=a['spacing']:raise ValueError('V4 curve profile mismatch')
 v4=deepcopy(v4_curve);v3=deepcopy(v3_curve);storage=hook_storage.copy()
 first=v4.swap(False,a['amount'],a['limit'])
 if first['unfilled']:raise ValueError('partial upstream fill')
 fee=accounting_update(storage,hook_config,-first['amount0'],**accounting_slots)
 native_to_wrap=native_balance+fee['net'];available=weth_balance+native_to_wrap
 if max(native_to_wrap,available)>=1<<256:raise ValueError('bridge inventory overflow')
 leg=intent(third_action,available,[pool_meta])
 if leg['token_in']!=WETH or v3.fee!=int(pool_meta['fee']) or v3.spacing!=int(pool_meta['spacing']):
  raise ValueError('downstream bridge profile mismatch')
 final=v3.swap(leg['zero'],leg['amount'],leg['limit'])
 if final['unfilled']:raise ValueError('partial downstream fill')
 storage.update(fee['writes'])
 return dict(v4_curve=v4,v3_curve=v3,hook_storage=storage,v4_fill=first,hook_fee=fee,v3_intent=leg,v3_fill=final,
  weth_balance=available-leg['amount'],native_balance=0,native_to_wrap=native_to_wrap,
  execution_complete=False,assumptions=['verified hook branch','full token credit and wrap','transaction success'])
