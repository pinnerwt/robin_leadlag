"""Shared live/replay policy. Decimal math, state quotes only, no I/O.

The reference BBO is a signal, not a hedge or guaranteed future exit.
Position mark uses Binance ask converted to USDG. Market appreciation may
push existing inventory above cap; this blocks buys, never invents a fill.
"""
from dataclasses import dataclass
from decimal import Decimal,localcontext,ROUND_FLOOR
D=Decimal

@dataclass(frozen=True)
class Policy:
 max_position_usdg:D
 edge_bps:D
 delay_ns:int=150_000_000
 max_bbo_age_ns:int=1_000_000_000
 fx:D=D('1')
 gas:D=D('0')
 exit_edge_bps:D|None=None
 def __post_init__(self):
  for x in (self.max_position_usdg,self.edge_bps,self.fx,self.gas):
   if not x.is_finite():raise ValueError('nonfinite policy')
  if self.max_position_usdg<=0 or self.edge_bps<0 or self.fx<=0 or self.gas<0 or self.delay_ns<0 or self.max_bbo_age_ns<0:raise ValueError('invalid policy')
  if self.exit_edge_bps is not None and (not self.exit_edge_bps.is_finite() or self.exit_edge_bps<0):raise ValueError('invalid exit edge')

@dataclass(frozen=True)
class Inventory:
 base:D=D('0')
 cash:D=D('500')

def quantities(policy,inventory,reference_ask,decimals):
 if not inventory.base.is_finite() or not inventory.cash.is_finite() or inventory.base<0 or inventory.cash<0:raise ValueError('negative inventory')
 if type(decimals) is not int or not 0<=decimals<=36:raise ValueError('invalid base decimals')
 if not reference_ask.is_finite() or reference_ask<=0:raise ValueError('invalid reference ask')
 with localcontext() as c:
  c.prec=100;unit=D(10)**-decimals
  # Quote the maximum remaining position size, not a fixed 0.1 token.
  room=max(D(0),min(policy.max_position_usdg-inventory.base*reference_ask,inventory.cash-policy.gas))
  buy=(room/reference_ask).quantize(unit,rounding=ROUND_FLOOR)
  sell=inventory.base.quantize(unit,rounding=ROUND_FLOOR)
  return dict(buy=buy,sell=sell)

def side_available(quote,side):
 """A revert on the opposite side must not suppress a valid executable quote."""
 return (quote.get('status') in ('priced','partial') and quote.get('state_valid',False)
         and quote.get('ask_usdg' if side=='buy' else 'bid_usdg') is not None)

def decide(policy,inventory,side,quantity,quote,bbo,now_ns,*,threshold_override=None):
 """quote amounts are total USDG; require a producer-validated state version."""
 if side not in ('buy','sell') or quantity<=0:return None
 if not side_available(quote,side):return None
 if D(quote['size_tokens'])!=quantity:raise ValueError('quote size mismatch')
 if not 0<=now_ns-int(quote['available_ns']):return None
 age=now_ns-int(bbo['available_ns'])
 if not 0<=age<=policy.max_bbo_age_ns:return None
 bid,ask=D(bbo['bid'])*policy.fx,D(bbo['ask'])*policy.fx
 if not bid.is_finite() or not ask.is_finite() or not 0<bid<=ask:return None
 with localcontext() as c:
  c.prec=100
  amount=D(quote['ask_usdg'] if side=='buy' else quote['bid_usdg'])
  if not amount.is_finite() or amount<=0:return None
  if side=='buy':
   if amount+policy.gas>inventory.cash or (inventory.base+quantity)*ask>policy.max_position_usdg:return None
   edge=(quantity*bid/(amount+policy.gas)-1)*10000;threshold=policy.edge_bps
  else:
   if quantity>inventory.base or amount<=policy.gas:return None
   edge=((amount-policy.gas)/(quantity*ask)-1)*10000
   threshold=policy.edge_bps if policy.exit_edge_bps is None else policy.exit_edge_bps
  if threshold_override is not None:
   threshold=D(threshold_override)
   if not threshold.is_finite() or threshold<=-10000:raise ValueError('invalid threshold override')
  if edge<threshold:return None
  return dict(side=side,size_tokens=str(quantity),amount_usdg=str(amount),edge_bps=str(edge),threshold_bps=str(threshold),signal_ns=now_ns,execute_after_ns=now_ns+policy.delay_ns,state_version=quote.get('state_version'))

def fill(policy,inventory,order,quote,bbo,now_ns):
 """Requote the ORIGINAL size at arrival, never substitute a future swap price."""
 if now_ns<order['execute_after_ns']:return None
 q=D(order['size_tokens']);candidate=decide(policy,inventory,order['side'],q,quote,bbo,now_ns)
 if candidate is None:return None
 amount=D(candidate['amount_usdg'])
 with localcontext() as c:
  c.prec=100
  position=Inventory(inventory.base+q,inventory.cash-amount-policy.gas) if order['side']=='buy' else Inventory(inventory.base-q,inventory.cash+amount-policy.gas)
 return position,dict(candidate,filled_ns=now_ns,original_signal_ns=order['signal_ns'])
