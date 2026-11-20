"""Original calldata to two-pool state preview, with explicit optimistic mode."""
from variant_batch_route import inspect
from variant_v3_bridge import preview
from delegated_settler_tail import intent as tail_intent

def preview_raw(calldata,*,curves,pools,anchors,weth_balance,usdg_balance,assume_success=False):
 if type(usdg_balance) is not int or not 0<=usdg_balance<1<<256:raise ValueError('invalid USDG inventory')
 plan=inspect(calldata,pools);first,last=plan['pools'];actions=plan['holder']['actions']
 if first not in curves or last not in curves:raise ValueError('missing bound pool curve')
 result=preview(actions[0]['data'],actions[1]['data'],upstream=curves[first],downstream=curves[last],pools=pools,anchors=anchors,weth_balance=weth_balance)
 balance=usdg_balance-result['downstream_fill']['amount1']
 if not 0<=balance<1<<256:raise ValueError('USDG inventory overflow')
 tail=tail_intent(actions[2]['data'],balance);minimum=plan['holder']['min_output'];violations=[]
 if tail['remaining']<minimum:violations.append(dict(kind='settler_min_output',required=minimum,available=tail['remaining']))
 sweep=min(tail['remaining'],max(minimum,tail['remaining']-1));outer_min=plan['router']['minimum_word']
 if not sweep or sweep<outer_min:violations.append(dict(kind='outer_router_min_output',required=outer_min,available=sweep))
 if violations and not assume_success:raise ValueError('minimum output not met')
 return dict(**result,curves={first:result['upstream'],last:result['downstream']},tail=tail,usdg_balance=tail['remaining']-sweep,outer_router_receipt=sweep,known_violations=violations,success_assumed=assume_success,plan=plan,complete_scope_verified=False)
