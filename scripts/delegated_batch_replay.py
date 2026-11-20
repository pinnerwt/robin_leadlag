"""Guarded sequential research replay for initialized batch bridge state.

Feed EVERY source transaction with a contiguous source ordinal. An unknown
transaction invalidates the replay; address non-membership is not proof of
irrelevance. Source transport gaps must also call invalidate(). This component
is not wired into live Book and does not upgrade partial execution coverage.
"""
from copy import deepcopy
from initialize_batch_bridge import initialize
from delegated_batch_preview import preview_raw

class BatchReplay:
 def __init__(self,seed,quotes,initial_calldata,*,inventory,transaction_target,last_ordinal,assume_success=False):
  if type(last_ordinal) is not int or last_ordinal< -1:raise ValueError('invalid starting ordinal')
  self._params=initialize(seed,quotes,initial_calldata,inventory=inventory,transaction_target=transaction_target)
  self.target=transaction_target.lower();self.last_ordinal=last_ordinal;self.assume_success=assume_success
  self.invalid_reason=None;self._last_tx=None;self._last_result=None
 def invalidate(self,reason):
  if not self.invalid_reason:self.invalid_reason=str(reason) or 'unspecified gap'
 def snapshot(self):return deepcopy(self._params)
 def apply(self,tx,ordinal):
  if self.invalid_reason:raise ValueError('replay invalid: '+self.invalid_reason)
  if type(ordinal) is not int or ordinal<0:
   self.invalidate('invalid source ordinal');raise ValueError(self.invalid_reason)
  if ordinal==self.last_ordinal and tx==self._last_tx:return deepcopy(self._last_result)
  if ordinal!=self.last_ordinal+1:
   self.invalidate('source gap, conflict or out-of-order transaction');raise ValueError(self.invalid_reason)
  raw=tx.get('raw_transaction')
  if not isinstance(raw,str) or not raw.startswith('0x') or len(raw)<4:
   self.invalidate('missing transaction envelope');raise ValueError(self.invalid_reason)
  try:envelope=bytes.fromhex(raw[2:])
  except ValueError:
   self.invalidate('malformed transaction envelope');raise ValueError(self.invalid_reason)
  if not envelope or envelope[0]==4:
   self.invalidate('delegation may have changed; fresh checkpoint required');raise ValueError(self.invalid_reason)
  if (tx.get('to') or '').lower()!=self.target or not tx.get('data','').startswith('0xc3c16ee4'):
   self.invalidate('unmodeled transaction may affect dependencies');raise ValueError(self.invalid_reason)
  try:result=preview_raw(tx['data'],**self._params,assume_success=self.assume_success)
  except (ValueError,KeyError) as error:
   self.invalidate('state transition unavailable: '+str(error));raise ValueError(self.invalid_reason) from error
  # Commit only after the entire local preview succeeds. Never overwrite flags
  # that say execution/scope remain incomplete, even under success assumption.
  next_params=deepcopy(self._params)
  for key in ('v4_curve','v3_curve','hook_storage','weth_balance','native_balance'):
   next_params['bridge_state'][key]=result[key]
  next_params['usdg_balance']=result['usdg_balance']
  self._params=next_params;self.last_ordinal=ordinal;self._last_tx=deepcopy(tx);self._last_result=deepcopy(result)
  return deepcopy(result)
