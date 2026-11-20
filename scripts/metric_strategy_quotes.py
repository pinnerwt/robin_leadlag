"""Size selection shared by the Metric recorder and state-based replay."""
from decimal import Decimal as D
from metric_strategy import quantities

def quote_plan(worker,policy,inventory,pool,bbo,*,state_valid,state_version,header=None):
 meta=worker.pools[pool.lower()]
 sizes=quantities(policy,inventory,D(bbo['ask'])*policy.fx,int(meta['decimals'][0]))
 cache={};result=[]
 for side,q in sizes.items():
  if not q:continue
  if q not in cache:cache[q]=worker.quote(pool,str(q),header=header)
  quote=dict(cache[q],side=side,state_valid=state_valid,state_version=state_version,max_position_usdg=str(policy.max_position_usdg))
  if quote['status']=='priced':
   scale=D(10)**int(meta['decimals'][1]);quote['bid_usdg']=str(D(quote['bid_amount_raw'])/scale);quote['ask_usdg']=str(D(quote['ask_amount_raw'])/scale)
  result.append(quote)
 return result
