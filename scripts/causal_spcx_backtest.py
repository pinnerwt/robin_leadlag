"""Two-view arrival-order, single-leg, price-taker research backtest; no network.
Decision state learns sender aliases only on arriving logs. Truth uses accepted
historical updates for fill evaluation, never for selecting the signal.
Own size impact/fees are quoted but own fills do not alter future historic state.
"""
import argparse,collections,heapq,json,subprocess,time
from decimal import Decimal as D, ROUND_FLOOR
from pathlib import Path
from metric_strategy import Policy,Inventory,quantities,decide,side_available

class Worker:
 def __init__(self,path,mode='source-only'):
  if mode not in ('source-only','provider-full'):raise ValueError('invalid provider mode')
  self.p=subprocess.Popen(['target/release/examples/spcx_state_worker',path,'--'+mode],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True,bufsize=1)
  self.version=0;self.cache={};self.errors=collections.Counter();self.age_buckets=collections.Counter();self.source_timestamp_ms=None
  seed=json.loads(Path(path).read_text());pool=seed['pools'][0] if len(seed['pools'])==1 else next(p for p in seed['pools'] if p.get('binance_symbol')=='SPCXBUSDT')
  slot=pool.get('source_slot','0x8dfdc825dd0453e7c80b1c1d32ae910e35d6efe9000000000000000000000054')
  word=seed['accounts'].get('0xe844701934d9c6085b292e428f41b911cc0b3872',{}).get('storage',{}).get(slot)
  if word:self.source_timestamp_ms=(int(word,16)>>8)&((1<<56)-1)
  self.aux_feed_id=pool.get('aux_feed_id');self.aux_timestamp_ms=None
  if self.aux_feed_id is not None:self.aux_timestamp_ms=self.call(dict(kind='aux_info',feed=self.aux_feed_id))['publish_ms']
 def call(self,r):
  self.p.stdin.write(json.dumps(r)+'\n');self.p.stdin.flush();line=self.p.stdout.readline()
  if not line:raise RuntimeError('worker ended')
  out=json.loads(line)
  if 'error' in out:raise ValueError(out['error'])
  return out['result']
 def change(self,r):
  out=self.call(r)
  if out.get('changed',True):
   self.version+=1;self.cache.clear()
   if r.get('kind')=='source':self.source_timestamp_ms=(int(r['word'],16)>>8)&((1<<56)-1)
  if r.get('kind')=='aux_oracle':
   for u in out.get('tracked',[]):
    if u['feed']==self.aux_feed_id:self.aux_timestamp_ms=max(self.aux_timestamp_ms or 0,u['publish_ms'])
  return out
 def quote(self,q,now,header,origin):
  raw=int(q*D(10)**18);h=dict(header);h['timestamp']=hex(max(int(h['timestamp'],16),(origin+now)//10**9))
  key=(self.version,raw,h['timestamp'],h['l1BlockNumber'])
  if key not in self.cache:
   try:
    v=self.call(dict(kind='quote',raw_base=str(raw),header=h))
    amounts={side+'_usdg':str(D(v[side+'_raw'])/10**6) if v.get(side+'_raw') is not None else None for side in ('bid','ask')}
    n=sum(x is not None for x in amounts.values());errors={side:v.get(side+'_error') for side in ('bid','ask') if v.get(side+'_error')}
    for side,error in errors.items():self.errors[side+': '+error]+=1
    self.cache[key]=dict(status='priced' if n==2 else 'partial' if n else 'unavailable',state_valid=True,size_tokens=str(q),**amounts,state_version=self.version,side_errors=errors,reason='; '.join(side+': '+e for side,e in errors.items()) or None)
   except ValueError as e:self.errors[str(e)]+=1;self.cache[key]=dict(status='unavailable',state_valid=False,size_tokens=str(q),reason=str(e))
  age=None if self.source_timestamp_ms is None else (origin+now)/1e6-self.source_timestamp_ms
  block_age=None if self.source_timestamp_ms is None else int(h['timestamp'],16)*1000-self.source_timestamp_ms
  self.age_buckets[str(None if block_age is None else int(block_age//1000))+':'+self.cache[key]['status']]+=1
  return dict(self.cache[key],available_ns=now,source_timestamp_ms=self.source_timestamp_ms,source_age_ms=age,provider_block_source_age_ms=block_age,aux_age_ms=None if self.aux_timestamp_ms is None else (origin+now)/1e6-self.aux_timestamp_ms,provider_block_aux_age_ms=None if self.aux_timestamp_ms is None else int(h['timestamp'],16)*1000-self.aux_timestamp_ms)
 def close(self):
  self.p.stdin.close();self.p.wait(timeout=10);self.p.stdout.close()

def advance_header(current,new):
 # Never run a state from a newer block against an older extension clock.
 return dict(current,**{k:hex(max(int(current[k],16),int(new[k],16))) for k in ('timestamp','l1BlockNumber')})

def resolve_route(route):
 """Translate observed Taiwan receipt times onto an Ohio wall-clock timeline.
 Truth is at inferred chain emission; decision data includes local feed latency.
 Legacy routes retain their original receipt-time execution proxy.
 """
 if 'latency_ms' not in route:return dict(route)
 l=route['latency_ms']
 keys=('tokyo_to_taiwan','tokyo_to_ohio','chain_to_taiwan','chain_to_ohio_machine','ohio_machine_to_chain')
 v={k:D(str(l[k])) for k in keys}
 if any(not x.is_finite() or x<0 for x in v.values()):raise ValueError('invalid route latency')
 if any(k in route for k in ('binance_shift_ms','chain_shift_ms','truth_chain_shift_ms','execution_ms')):
  raise ValueError('use latency_ms or explicit shifts, not both')
 return dict(route,binance_shift_ms=float(v['tokyo_to_ohio']-v['tokyo_to_taiwan']),
             chain_shift_ms=float(v['chain_to_ohio_machine']-v['chain_to_taiwan']),
             truth_chain_shift_ms=float(-v['chain_to_taiwan']),
             execution_ms=float(v['ohio_machine_to_chain']))

def run(config,route,events,bbos,pool_observer=None):
 route=resolve_route(route)
 seed=json.loads(Path(config['checkpoint']).read_text());anchor=int(seed['anchor']['number'],16)
 session=next(r for r in events if r['kind']=='session');origin=session['start_utc_ns']
 start=max(int(config['warmup_seconds']*1e9),seed['finished_ns']-origin)
 ds=int(route['chain_shift_ms']*1e6);bs=int(route['binance_shift_ms']*1e6);delay=int(route['execution_ms']*1e6)
 ts=int(route.get('truth_chain_shift_ms',route['chain_shift_ms'])*1e6)
 mode=config.get('provider_mode','source-only');decision=Worker(config['checkpoint'])if mode=='source-only'else Worker(config['checkpoint'],mode);truth=Worker(config['checkpoint'])if mode=='source-only'else Worker(config['checkpoint'],mode);queue=[];serial=0
 def push(t,priority,kind,r):
  nonlocal serial
  serial+=1
  execution=kind in ('truth_source','truth_pool','truth_aux','truth_v3')
  block=int(r.get('block_number','0x0'),16) if execution else 0
  txindex=(int(r.get('transaction_index','0x0'),16),min([int(x.get('logIndex','0x0'),16) for x in r.get('logs',[])] or [int(r.get('log',{}).get('logIndex','0x0'),16)])) if execution else (0,0)
  heapq.heappush(queue,(int(t),0 if execution else priority,block,txindex,serial,kind,r))
 edge_samples={'buy':[],'sell':[]};aliases=set();patches={};stats=collections.Counter();bbo=None;header=dict(seed['anchor']);truth_header=dict(seed['anchor']);truth_valid=True;decision_valid=True
 phase_mode='open_close_grid' in config
 entry_side=config.get('entry_side','sell')
 if entry_side not in ('buy','sell'):raise ValueError('entry_side')
 phase_grid=config.get('open_close_grid',[])
 for g in phase_grid:
  if 'execution_ms'in g and (not D(str(g['execution_ms'])).is_finite() or D(str(g['execution_ms']))<0):raise ValueError('invalid scenario latency')
  if not D(g['open_bps']).is_finite() or D(g['open_bps'])<0 or not D(g['close_bps']).is_finite() or D(g['close_bps'])<=-10000:raise ValueError('invalid open/close thresholds')
 grid=[dict(buy_bps=g['open_bps'],sell_bps=g['open_bps']) for g in phase_grid] if phase_mode else config.get('threshold_grid',[dict(buy_bps=y,sell_bps=config['exit_edge_bps'] if config['exit_edge_bps'] is not None else y) for y in config['edges_bps']])
 policies=[Policy(D(config['max_position_usdg']),D(g['buy_bps']),delay_ns=int(D(str(phase_grid[i].get('execution_ms',route['execution_ms'])))*1000000) if phase_mode else delay,max_bbo_age_ns=config['max_bbo_age_ms']*10**6,fx=D(config['usdg_per_usdt']),gas=D(config['gas_usdg']),exit_edge_bps=D(g['sell_bps'])) for i,g in enumerate(grid)]
 states=[];initial=None;baseline_mode=config.get('fixed_baseline',False);last_observed=None
 from baseline_policy import policy_at_baseline, sizes as baseline_sizes
 for r in events:
  if r['kind']=='oracle_candidate':
   if r.get('sender_recovered') is False and not config.get('assume_tracked_word_id',False):raise ValueError('sender aliases require recovered sender')
   if r.get('block_number') is None:stats['missing_block_metadata']+=1;continue
   after=int(r['block_number'],16)>anchor
   if 'accepted_log_ns' in r:
    if after:push(r['mono_ns']+ts,0,'truth_source',r)
    push(max(r['accepted_log_ns'],r['mono_ns'])+ds,2,'learn_alias',r)
   if after:push(r['mono_ns']+ds,3,'source',r)
  if r['kind']=='aux_oracle' and r.get('block_number') and int(r['block_number'],16)>anchor:
   push(r['mono_ns']+ts,0,'truth_aux',r);push(r['mono_ns']+ds,3,'aux',r)
  if r['kind']=='v3_price' and int(r['block_number'],16)>anchor:
   push(r['mono_ns']+ts,0,'truth_v3',r);push(r['log_mono_ns']+ds,3,'v3',r)
  if r['kind']=='pool_transaction' and int(r['block_number'],16)>anchor:
   push(r['mono_ns']+ts,1,'truth_pool',r);push(r['log_mono_ns']+ds,4,'pool_patch',r)
 for r in bbos:push(r['mono_ns']+bs,5,'bbo',r)
 end=max(r['mono_ns']+bs for r in bbos)
 if pool_observer is not None:
  if not config.get('hy_fixed_quantity'):raise ValueError('pool HY needs reference-independent fixed quantity')
  for tick in range(int(start),int(end)+1,1_000_000_000):push(tick,5,'quote_tick',{})
 elapsed=time.monotonic();processed=0
 try:
  while queue:
   now,priority,_,_,_,kind,r=heapq.heappop(queue)
   if now>end:break
   processed+=1;trigger=False
   if kind in ('truth_v3','v3'):
    w=truth if kind=='truth_v3' else decision
    try:
     out=w.change(r);stats[kind+'_updates']+=int(out.get('changed',False));trigger=kind=='v3' and out.get('changed',False)
     if kind=='truth_v3':truth_header=r['header']
     elif r['mono_ns']<=r['log_mono_ns']:header=advance_header(header,r['header'])
     else:
      header=dict(header);header['timestamp']=hex(max(int(header['timestamp'],16),int(r['log'].get('blockTimestamp',header['timestamp']),16)))
    except ValueError as exc:
     stats[kind+'_error:'+str(exc)]+=1
     if kind=='truth_v3':truth_valid=False
     else:decision_valid=False
   elif kind in ('truth_aux','aux'):
    w=truth if kind=='truth_aux' else decision
    try:
     out=w.change(r);stats[kind+'_updates']+=int(out.get('changed',False));trigger=kind=='aux' and out.get('changed',False)
     if kind=='truth_aux':truth_header=advance_header(truth_header,r['header'])
     else:header=advance_header(header,r['header'])
    except ValueError as exc:
     stats[kind+'_error:'+str(exc)]+=1
     if kind=='truth_aux':truth_valid=False
     else:decision_valid=False
   elif kind=='truth_source':
    truth.change(dict(kind='source',word=r['word']));truth_header=r['header']
   elif kind=='truth_pool':
    truth_header=r['header']
    try:response=truth.change(dict(kind='pool',logs=r['logs'],header=r['header']));patches[r['tx']]=response['patch'];stats['truth_pool_updates']+=1;stats['observed_swap_token_mismatch']+=response['diagnostic'].get('token_mismatch_count',int(response['diagnostic'].get('token_delta_exact') is False));stats['observed_swap_count']+=response['diagnostic'].get('swap_count',0);stats['max_observed_price_error_bps']=max(stats['max_observed_price_error_bps'],response['diagnostic'].get('max_price_error_bps',0))
    except ValueError as e:truth_valid=False;patches[r['tx']]=None;stats['truth_pool_failure:'+str(e)]+=1
   elif kind=='learn_alias':
    first=r['from'].lower() not in aliases;aliases.add(r['from'].lower())
    if first:stats['aliases_learned']+=1
    if not config.get('assume_tracked_word_id',False) and int(r['block_number'],16)>anchor:
     out=decision.change(dict(kind='source',word=r['word']));trigger=out.get('changed',False);stats['log_source_corrections']+=int(trigger)
     if trigger:header=advance_header(header,r['header'])
   elif kind=='source':
    if config.get('assume_tracked_word_id',False) or r['from'].lower() in aliases:
     out=decision.change(dict(kind='source',word=r['word']));header=advance_header(header,r['header']);trigger=out.get('changed',False);stats['calldata_source_updates']+=int(trigger)
    else:stats['unknown_sender_candidates']+=1
   elif kind=='pool_patch':
    patch=patches.get(r['tx'])
    if patch is None and r['tx'] not in patches:
     # Pool push log arrived before its Nitro frame. Reduce the observed log
     # against decision state now; never wait for or read the future truth patch.
     try:
      known_header=dict(header);known_header['timestamp']=hex(max(int(header['timestamp'],16),(origin+now)//10**9))
      decision.change(dict(kind='pool',logs=r['logs'],header=known_header));trigger=True;stats['early_log_depth_updates']+=1;stats['log_depth_updates']+=1
     except ValueError as e:decision_valid=False;stats['early_log_depth_failure:'+str(e)]+=1
    elif patch is None:decision_valid=False;stats['decision_pool_missing_patch']+=1
    else:decision.change(dict(kind='patch',patch=patch));header=advance_header(header,r['header']);trigger=True;stats['log_depth_updates']+=1
   elif kind=='bbo':
    if r.get('invalid',False):
     # Keep the last mark for reporting, but disallow signals until a valid
     # quote arrives after a crossed quote or a reference-feed disconnect.
     if bbo is not None:bbo=dict(bbo,available_ns=-10**30)
     trigger=False
    else:bbo=dict(bid=r['bid'],ask=r['ask'],available_ns=now);trigger=True
   elif kind=='fill':
    i=r['scenario'];s=states[i];order=s['pending'];s['pending']=None
    if order is None:continue
    if not truth_valid:s['cancelled']['truth_unavailable']+=1;continue
    q=D(order['size_tokens']);v=truth.quote(q,now,truth_header,origin)
    if not side_available(v,order['side']):
     s['cancelled']['execution_quote_unavailable']+=1;s['rejections'].append(dict(reason='execution_quote_unavailable',side=order['side'],signal_ns=order['signal_ns'],attempt_ns=now,provider_error=v.get('reason'),signal_source_age_ms=order.get('source_age_ms'),execution_source_age_ms=v.get('source_age_ms'),provider_block_source_age_ms=v.get('provider_block_source_age_ms'),signal_aux_age_ms=order.get('aux_age_ms'),execution_aux_age_ms=v.get('aux_age_ms'),provider_block_aux_age_ms=v.get('provider_block_aux_age_ms')));continue
    side=order['side'];amount=D(v['ask_usdg'] if side=='buy' else v['bid_usdg']);policy=policies[i];inv=s['inv'];limit=D(order['limit_usdg'])
    # Submitted limits only. No future Binance threshold recheck at execution.
    if (side=='buy' and (amount>limit or amount+policy.gas>inv.cash)) or (side=='sell' and (amount<limit or q>inv.base)):
     s['cancelled']['submitted_limit']+=1;s['rejections'].append(dict(reason='submitted_limit',side=side,signal_ns=order['signal_ns'],attempt_ns=now,signal_amount_usdg=order['amount_usdg'],execution_amount_usdg=str(amount),limit_usdg=str(limit),adverse_slippage_bps=str(((D(order['amount_usdg'])-amount)/D(order['amount_usdg']) if side=='sell' else (amount-D(order['amount_usdg']))/D(order['amount_usdg']))*10000)));continue
    if side=='buy':s['inv']=Inventory(inv.base+q,inv.cash-amount-policy.gas);s['basis']+=amount+policy.gas
    else:
     cost=s['basis']*q/inv.base;s['realized']+=amount-policy.gas-cost;s['basis']-=cost;s['inv']=Inventory(inv.base-q,inv.cash+amount-policy.gas)
    if phase_mode:
     if order['phase']=='open':
      s['is_open']=True;s['cycle_start']=dict(fill_ns=now,base=str(inv.base),cash=str(inv.cash),side=side,size_tokens=str(q),amount_usdg=str(amount))
     else:
      start_cycle=s['cycle_start'];end_inv=s['inv'];mark=D(bbo['bid'])*policy.fx
      excess=(end_inv.cash-D(start_cycle['cash']))+(end_inv.base-D(start_cycle['base']))*mark
      s['cycles'].append(dict(open=start_cycle,close_ns=now,close_size_tokens=str(q),close_amount_usdg=str(amount),duration_ns=now-start_cycle['fill_ns'],excess_vs_episode_hold_usdg=str(excess),mark_bid_usdg=str(mark)))
      if not baseline_mode or end_inv.base==D(initial['base_tokens']):
       s['is_open']=False;s['cycle_start']=None
      else:
       s['cycles'].pop()
    s['fills'].append(dict(phase=order.get('phase'),side=side,size_tokens=str(q),amount_usdg=str(amount),signal_ns=order['signal_ns'],fill_ns=now,edge_at_signal_bps=order['edge_bps'],limit_usdg=order['limit_usdg'],signal_binance_bid=order['signal_binance_bid'],signal_binance_ask=order['signal_binance_ask'],signal_source_age_ms=order.get('source_age_ms'),execution_source_age_ms=v.get('source_age_ms'),provider_block_source_age_ms=v.get('provider_block_source_age_ms'),signal_aux_age_ms=order.get('aux_age_ms'),execution_aux_age_ms=v.get('aux_age_ms'),provider_block_aux_age_ms=v.get('provider_block_aux_age_ms')))
   if pool_observer is not None and now>=start and kind in ('source','aux','v3','pool_patch','quote_tick'):
    observation_key=(decision.version,(origin+now)//10**9,header['timestamp'],header['l1BlockNumber'],decision_valid)
    if observation_key!=last_observed:
     fixed_q=D(config['hy_fixed_quantity'])
     v=decision.quote(fixed_q,now,header,origin) if decision_valid else dict(status='unavailable',reason='decision state invalid')
     pool_observer(origin+now,fixed_q,v);last_observed=observation_key
   if config.get('quote_only',False):continue
   if not trigger or now<start or bbo is None or not decision_valid:continue
   if now-bbo['available_ns']>config['max_bbo_age_ms']*10**6:continue
   if initial is None:
    fx=policies[0].fx;cash=D(config.get('initial_cash_usdg',config['max_position_usdg']))
    notional=D(config.get('initial_inventory_usdg','0'))
    base=(notional/(D(bbo['ask'])*fx)).quantize(D('1e-18'),rounding=ROUND_FLOOR) if notional else D(config.get('initial_position_tokens','0'))
    if base<0 or cash<0:raise ValueError('negative initial portfolio')
    basis_price=D(config['initial_mark_price_usdg']) if 'initial_mark_price_usdg' in config else D(bbo['bid'])*fx
    basis=base*basis_price
    initial=dict(available_ns=now,base_tokens=str(base),cash_usdg=str(cash),bid=bbo['bid'],ask=bbo['ask'],equity_usdg=str(cash+basis),basis_is_initial_bid_mark=True,basis_price_usdg=str(basis_price),common_initial_mark='initial_mark_price_usdg' in config)
    states=[dict(inv=Inventory(base,cash),pending=None,fills=[],rejections=[],cancelled=collections.Counter(),basis=basis,realized=D(0),is_open=False,cycle_start=None,cycles=[]) for _ in policies]
   if config.get('diagnostic_probes',True):
    probe=quantities(policies[0],Inventory(cash=D(config['max_position_usdg'])),D(bbo['ask'])*policies[0].fx,18)['buy']
    probe_quote=decision.quote(probe,now,header,origin)
    stats['probe_evaluations']+=1;stats['probe_unavailable']+=int(probe_quote['status']!='priced')
    if side_available(probe_quote,'buy'):
     edge_samples['buy'].append(float((probe*D(bbo['bid'])*policies[0].fx/D(probe_quote['ask_usdg'])-1)*10000))
    if side_available(probe_quote,'sell'):
     edge_samples['sell'].append(float((D(probe_quote['bid_usdg'])/(probe*D(bbo['ask'])*policies[0].fx)-1)*10000))
   evaluation_cache={}
   for i,(policy,s) in enumerate(zip(policies,states)):
    baseline=D(initial['base_tokens'])
    size_policy=policy
    def requested_sizes():
     return baseline_sizes(size_policy,s['inv'],baseline,D(bbo['ask'])*policy.fx,18) if baseline_mode else quantities(policy,s['inv'],D(bbo['ask'])*policy.fx,18)
    if s['pending'] is not None:continue
    # Cache only a proven no-order decision. Orders/rejections are never suppressed.
    # These fields determine both exact quotes, policy inputs and fresh-BBO validity.
    eval_key=(decision.version if hasattr(decision,'version') else None,bbo['bid'],bbo['ask'],s['inv'].base,s['inv'].cash,(origin+now)//10**9,header['timestamp'],header['l1BlockNumber'],s.get('is_open',False))
    if config.get('cache_no_order',False) and s.get('no_order_key')==eval_key:continue
    if baseline_mode:policy=policy_at_baseline(policy,baseline,D(bbo['ask'])*policy.fx)
    if phase_mode and config.get('share_candidate_evaluations',False):
     phase='close' if s['is_open'] else 'open';threshold=D(phase_grid[i]['close_bps'] if s['is_open'] else phase_grid[i]['open_bps'])
     side=('buy' if entry_side=='sell' else 'sell') if s['is_open'] else entry_side
     if eval_key not in evaluation_cache:
      q=requested_sizes()[side];candidate=None
      if q>0:
       v=decision.quote(q,now,header,origin)
       if side=='buy':
        for _ in range(4):
         if not side_available(v,'buy') or D(v['ask_usdg'])+policy.gas<=s['inv'].cash:break
         q=(q*(s['inv'].cash-policy.gas)/D(v['ask_usdg'])*D('0.999999999')).quantize(D('1e-18'),rounding=ROUND_FLOOR)
         if q<=0:break
         v=decision.quote(q,now,header,origin)
       candidate=decide(policy,s['inv'],side,q,v,bbo,now,threshold_override=D('-9999'))
       if candidate:candidate['source_age_ms']=v.get('source_age_ms');candidate['provider_block_source_age_ms']=v.get('provider_block_source_age_ms');candidate['aux_age_ms']=v.get('aux_age_ms')
      evaluation_cache[eval_key]=candidate
     candidate=evaluation_cache[eval_key]
     if candidate and D(candidate['edge_bps'])>=threshold:
      order=dict(candidate,phase=phase,threshold_bps=str(threshold),execute_after_ns=now+policy.delay_ns)
      amount=D(order['amount_usdg']);slip=D(config['slippage_bps'])/10000
      limit=min(s['inv'].cash-policy.gas,amount*(1+slip)) if side=='buy' else amount*(1-slip)
      order.update(limit_usdg=str(limit),signal_binance_bid=bbo['bid'],signal_binance_ask=bbo['ask']);s['pending']=order;push(now+policy.delay_ns,6,'fill',{'scenario':i})
    else:
     sizes=requested_sizes()
     phase='close' if s['is_open'] else 'open'
     threshold=D(phase_grid[i]['close_bps'] if s['is_open'] else phase_grid[i]['open_bps']) if phase_mode else None
     sides=(('buy' if entry_side=='sell' else 'sell') if s['is_open'] else entry_side,) if phase_mode else ('sell','buy')
     for side in sides:
      q=sizes[side]
      if q<=0:continue
      v=decision.quote(q,now,header,origin)
      if phase_mode and side=='buy':
       # A negative close edge may pay above Binance ask. Resize using the
       # current local pool quote so budget, rather than a reference price, binds.
       for _ in range(4):
        if not side_available(v,'buy') or D(v['ask_usdg'])+policy.gas<=s['inv'].cash:break
        q=(q*(s['inv'].cash-policy.gas)/D(v['ask_usdg'])*D('0.999999999')).quantize(D('1e-18'),rounding=ROUND_FLOOR)
        if q<=0:break
        v=decision.quote(q,now,header,origin)
      order=decide(policy,s['inv'],side,q,v,bbo,now,threshold_override=threshold)
      if order:order['source_age_ms']=v.get('source_age_ms');order['provider_block_source_age_ms']=v.get('provider_block_source_age_ms');order['aux_age_ms']=v.get('aux_age_ms')
      if order and phase_mode:order['phase']=phase
      if order:
       amount=D(order['amount_usdg']);slip=D(config['slippage_bps'])/10000
       limit=min(s['inv'].cash-policy.gas,amount*(1+slip)) if side=='buy' else amount*(1-slip)
       order['limit_usdg']=str(limit);order['signal_binance_bid']=bbo['bid'];order['signal_binance_ask']=bbo['ask'];s['pending']=order;push(now+policy.delay_ns,6,'fill',{'scenario':i});break
    if s['pending'] is None:s['no_order_key']=eval_key
  if config.get('quote_only',False):return dict(status='quote_only',truth_valid=truth_valid,decision_valid=decision_valid,statistics=dict(stats),decision_quote_errors=dict(decision.errors))
  if initial is None:
   if config.get('return_invalid_diagnostics',False):return dict(status='no_valid_initialization',statistics=dict(stats),truth_valid=truth_valid,decision_valid=decision_valid,decision_quote_errors=dict(decision.errors),execution_quote_errors=dict(truth.errors),decision_quote_age_buckets=dict(getattr(decision,'age_buckets',{})),execution_quote_age_buckets=dict(getattr(truth,'age_buckets',{})),results=[],wall_seconds=time.monotonic()-elapsed)
   raise ValueError('no valid initialization point')
  hold_equity=D(initial['cash_usdg'])+D(initial['base_tokens'])*D(bbo['bid'])*policies[0].fx
  hold_pnl=hold_equity-D(initial['equity_usdg'])
  results=[]
  for i,(policy,s) in enumerate(zip(policies,states)):
   inv=s['inv'];marked=inv.cash+inv.base*D(bbo['bid'])*policy.fx-D(initial['equity_usdg'])
   results.append(dict(edge_bps=str(policy.edge_bps),exit_edge_bps=str(policy.edge_bps if policy.exit_edge_bps is None else policy.exit_edge_bps),fills=s['fills'],rejections=s['rejections'],cancelled=dict(s['cancelled']),pending_at_end=s['pending'] is not None,base_tokens=str(inv.base),cash_usdg=str(inv.cash),realized_pnl_usdg=str(s['realized']),binance_mark_pnl_usdg=str(marked),hold_pnl_usdg=str(hold_pnl),excess_vs_hold_usdg=str(marked-hold_pnl),mark_is_not_liquidation=True))
   if phase_mode:results[-1].update(open_bps=phase_grid[i]['open_bps'],close_bps=phase_grid[i]['close_bps'],entry_side=entry_side,execution_ms=policy.delay_ns/1e6,cycles=s['cycles'],open_episode_at_end=s['is_open'])
  return dict(route=route,initial_portfolio=initial,start_ns=start,end_ns=end,statistics=dict(stats),decision_quote_errors=dict(decision.errors),execution_quote_errors=dict(truth.errors),decision_quote_age_buckets=dict(getattr(decision,'age_buckets',{})),execution_quote_age_buckets=dict(getattr(truth,'age_buckets',{})),truth_valid=truth_valid,decision_valid=decision_valid,results=results,directional_edge_diagnostics={side:{'observations':len(v),'max_bps':max(v) if v else None,'above_threshold_counts':{y:sum(e>=float(y) for e in v) for y in config['edges_bps']},'sell_is_hypothetical_without_inventory':side=='sell'} for side,v in edge_samples.items()},wall_seconds=time.monotonic()-elapsed)
 finally:decision.close();truth.close()

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--config',default='config/spcx-causal-backtest.json');p.add_argument('--route');p.add_argument('--output',required=True);a=p.parse_args();config=json.load(open(a.config));events=[json.loads(l) for l in open(config['events'])];bbos=[]
 for l in open(config['bbo_tape']):
  r=json.loads(l)
  if r['kind']=='bbo' and r['symbol']==config.get('symbol','SPCXBUSDT'):bbos.append(r)
 out={'config':config,'status':'conditional_price_taker_backtest','limitations':['Source-only provider guards/expiry not fully reproduced','Fill state uses translated Nitro ingress as a chain-time proxy, not verified inclusion time','Own size impact and fees quoted; own fills do not persist into future historical state','USDG/USDT parity and zero gas','Constant route shifts are hypothetical; no measured one-way latency or jitter'],'runs':[]}
 for route in config['routes']:
  if a.route and a.route!=route['name']:continue
  r=run(config,route,events,bbos);out['runs'].append(r);json.dump(out,open(a.output,'w'),indent=2)
  print(route['name'],[(s['edge_bps'],len(s['fills']),s['realized_pnl_usdg'],s['binance_mark_pnl_usdg']) for s in r['results']],flush=True)
