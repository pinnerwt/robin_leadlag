"""Raw-calldata quote-state preview. Offline integration, not live Book dispatch.
Caller supplies coherent initialized state and establishes code/hook branch pins.
Unresolved outer behavior and token side effects prevent complete execution claims.
"""
from delegated_batch_route import inspect
from delegated_settler_local import preview
from delegated_settler_tail import intent as tail_intent

def preview_raw(calldata,*,bridge_state,anchors,usdg_balance,assume_success=False):
 required={'v4','hook','v3','inventory'}
 if set(anchors)!=required or any(not isinstance(a,str) or not a for a in anchors.values()) or len(set(anchors.values()))!=1:
  raise ValueError('incoherent or missing state checkpoint anchors')
 if type(usdg_balance) is not int or not 0<=usdg_balance<1<<256:raise ValueError('USDG inventory bounds')
 plan=inspect(calldata,[bridge_state['pool_meta']]);actions=plan['holder']['actions']
 result=preview(actions[0]['data'],actions[2]['data'],**bridge_state)
 balance=usdg_balance-result['v3_fill']['amount1']
 if balance>=1<<256:raise ValueError('USDG inventory overflow')
 tail=tail_intent(actions[3]['data'],balance)
 minimum=plan['holder']['min_output'];violations=[]
 if tail['remaining']<minimum:violations.append(dict(kind='settler_min_output',required=minimum,available=tail['remaining']))
 # Preserve dust only when doing so still satisfies minimum output.
 sweep=min(tail['remaining'],max(minimum,tail['remaining']-1))
 outer_minimum=plan['router']['minimum_word']
 if sweep==0 or sweep<outer_minimum:violations.append(dict(kind='outer_router_min_output',required=outer_minimum,available=sweep))
 if violations and not assume_success:raise ValueError('minimum output not met: '+','.join(v['kind'] for v in violations))
 return dict(**result,tail=tail,outer_router_receipt=sweep,usdg_balance=tail['remaining']-sweep,
  decoded_plan=plan,checkpoint=next(iter(anchors.values())),known_violations=violations,
  success_assumed=assume_success,complete_scope_verified=False,
  remaining_guards=plan['unresolved']+['outer authorization and token side effects'])
