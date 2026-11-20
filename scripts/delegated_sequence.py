"""Provisional mode6 sequential preview. Callbacks must use local state only.

Does not implement action execution or token settlement. Unknown state/unsupported
operations propagate; only an explicitly modeled EVM revert discards a strategy.
"""
from copy import deepcopy
from delegated_compressed import inspect
from delegated_conditions import evaluate

class StrategyReverted(Exception):pass

def preview(calldata,state,*,read,execute):
 plan=inspect(calldata);groups=plan['condition_groups']
 if groups is None or len(groups)!=len(plan['strategies']):raise ValueError('unverified strategy conditions')
 working=deepcopy(state);attempted=[];mask=0
 for index,(strategy,group) in enumerate(zip(plan['strategies'],groups)):
  returns={(r['target'],r['calldata']):read(working,r) for r in group['records']}
  if not evaluate(group,returns)['passes']:continue
  attempted.append(index);candidate=deepcopy(working)
  try:execute(candidate,strategy,index)
  except StrategyReverted:continue
  working=candidate;mask|=1<<index
 if not mask:raise StrategyReverted('all strategies failed or skipped')
 return dict(state=working,attempted=attempted,success_mask=mask,execution_complete=False)
