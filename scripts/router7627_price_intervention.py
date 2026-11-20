"""Research price/tick intervention confined to one initialized-tick interval."""
from v3_state import tick_sqrt

def shift_no_crossing(state,new_sqrt,packed_slot):
 new_tick=tick_sqrt(new_sqrt)
 lo,hi=sorted((state.tick,new_tick))
 for tick in range(lo,hi+1):
  compressed=tick//state.spacing;word=compressed>>8;bit=compressed&255
  if word not in state.bitmap:raise ValueError('missing bitmap coverage')
  if state.bitmap[word]&(1<<bit):raise ValueError('price intervention crosses or touches initialized tick')
 if packed_slot&((1<<160)-1)!=state.sqrt:raise ValueError('slot/state price mismatch')
 old_tick=(packed_slot>>160)&((1<<24)-1)
 if old_tick!=(state.tick% (1<<24)):raise ValueError('slot/state tick mismatch')
 return (packed_slot>>184<<184)|((new_tick%(1<<24))<<160)|new_sqrt
