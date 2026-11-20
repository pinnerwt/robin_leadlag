"""Causal strategy replay driver, requiring an external validated state engine.

apply_event advances the real pool/provider state; quote_at re-simulates the
requested size against that state. No trade-price proxy or quote interpolation.
commit_fill must apply the simulated pool transition atomically and return True;
without an accepted state transition no fill is booked. Different Y scenarios
must use isolated inventory and simulated-impact state.
"""
from decimal import Decimal as D
from metric_strategy import Inventory,quantities,decide,fill

class Scenario:
 def __init__(self,policy,initial_cash=D('500')):
  self.policy=policy;self.initial_cash=initial_cash;self.positions={};self.pending={};self.fills=[];self.cancelled=0;self.last_ns=-1
 def step(self,event,quote_at,commit_fill):
  now=event['available_ns']
  if now<self.last_ns:raise ValueError('replay events out of arrival order')
  self.last_ns=now;token=event['token'];inventory=self.positions.setdefault(token,Inventory(cash=self.initial_cash))
  # Invalid state interrupts orders; it must never be forward-filled across gaps.
  if not event['state_valid']:
   self.cancelled+=int(self.pending.pop(token,None) is not None);return
  bbo=event['bbo'];order=self.pending.get(token)
  if order:
   if now<order['execute_after_ns']:return
   quote=quote_at(order['pool'],D(order['size_tokens']),now)
   outcome=fill(self.policy,inventory,order,quote,bbo,now);del self.pending[token]
   if outcome and commit_fill(order['pool'],order['side'],D(order['size_tokens']),now):
    self.positions[token],record=outcome;self.fills.append(dict(record,token=token,pool=order['pool'],actual_delay_ns=now-order['signal_ns']))
   else:self.cancelled+=1
   return
  sizes=quantities(self.policy,inventory,D(bbo['ask'])*self.policy.fx,event['base_decimals'])
  # Inventory-funded strategy: liquidate existing inventory when eligible;
  # otherwise increase it only up to remaining capacity. Never naked short.
  for side in ('sell','buy'):
   size=sizes[side]
   if size<=0:continue
   quote=quote_at(event['pool'],size,now);candidate=decide(self.policy,inventory,side,size,quote,bbo,now)
   if candidate:
    self.pending[token]=dict(candidate,pool=event['pool']);return
 def summary(self):
  return dict(edge_bps=str(self.policy.edge_bps),fills=len(self.fills),cancelled=self.cancelled,pending=len(self.pending),positions={t:dict(base=str(p.base),cash_usdg=str(p.cash)) for t,p in self.positions.items()},forced_close=False,gas_usdg_per_trade=str(self.policy.gas),pnl_status='open_inventory_requires_mark_and_cost_basis')
