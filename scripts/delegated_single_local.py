"""Optimistic standard V3 and explicit index4 quote-state route updates.

Funding fully credits the requested input; intermediate output fully credits the
next leg. No sender/condition/settlement validation. Unsupported actions reject.
Unrecorded suffixes may be skipped, but upstream dependencies must be available.
Index4 inputs include verified fee/cache/observation state for the caller; hints
in calldata are not charged fees. Post-hooks remain unevaluated, so this is
quote-state preview rather than complete execution or dependency validation.
"""
from copy import deepcopy
from delegated_single import inspect
from v3_state import MIN_SQRT,MAX_SQRT
ZERO='0x'+'00'*20

def preview(calldata,curves,metadata,recorded,*,index4=None,block=None,timestamp=None):
 plan=inspect(calldata);actions=plan['actions'];recorded=set(recorded)
 if plan['mode']!=128 or plan['header'][4]!=1:raise ValueError('unverified single-route execution mode')
 amount=plan['header'][3]
 if not 0<amount<1<<127:raise ValueError('single-route input bounds')
 # Validate the whole path before skipping a suffix. Unknown action kinds can
 # hide additional calls to recorded pools and therefore cannot be ignored.
 for i,a in enumerate(actions):
  if a['kind']!=1 or a['reserved'] or a['hook']!=ZERO:raise ValueError('unverified single-route action')
  if a['direction'] not in (0,1):raise ValueError('action direction')
  expected=(a['currency0'],a['currency1']) if a['direction'] else (a['currency1'],a['currency0'])
  if (a['token_in'],a['token_out'])!=expected:raise ValueError('action token direction')
  if i and actions[i-1]['token_out']!=a['token_in']:raise ValueError('disconnected route')
 relevant=[i for i,a in enumerate(actions) if a['target'] in recorded]
 end=max(relevant)+1 if relevant else 0
 working=deepcopy(curves);dynamic=deepcopy(index4 or {});fills=[]
 if set(working)&set(dynamic):raise ValueError('ambiguous pool state model')
 for a in actions[:end]:
  pool=a['target']
  if (pool not in working and pool not in dynamic) or pool not in metadata:raise ValueError('missing upstream pool state '+pool)
  curve=dynamic[pool].curve if pool in dynamic else working[pool];m=metadata[pool]
  if list(m['tokens'])!=[a['currency0'],a['currency1']] or (pool not in dynamic and curve.fee!=a['fee']) or curve.spacing!=a['spacing']:
   raise ValueError('pool profile mismatch '+pool)
  zero=bool(a['direction']);limit=MIN_SQRT+1 if zero else MAX_SQRT-1
  fee_info={}
  if pool in dynamic:
   from index4_local import PoolState
   if not isinstance(dynamic[pool],PoolState):raise ValueError('invalid index4 state model')
   change=dynamic[pool].preview_exact_input(block=block,timestamp=timestamp,zero=zero,amount=amount,limit=limit)
   dynamic[pool]=change['state'];fill=change['result'];fee_info={'charged_fee':change['fee'],'base_fee':change['base_fee']}
  else:fill=curve.swap(zero,amount,limit,True)
  if fill['unfilled']:raise ValueError('partial single-route fill not verified')
  amount=-fill['amount1' if zero else 'amount0']
  fills.append(dict(pool=pool,recorded=pool in recorded,**fee_info,**fill))
 return dict(index4=dynamic,post_hooks_evaluated=False,curves=working,fills=fills,skipped_suffix=actions[end:],
  stale_dependencies=sorted({a['target'] for a in actions[end:]}),
  transaction_success_assumed=True,full_token_credit_assumed=True,conditions_evaluated=False,
  execution_complete=False)
