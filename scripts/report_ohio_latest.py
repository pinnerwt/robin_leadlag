"""Summaries for research_ohio_latest; never select on held-out PnL."""
import argparse,json,datetime,collections,concurrent.futures
from pathlib import Path
from decimal import Decimal as D
import numpy as np
from iex_pool_hy import compare

def save(p,v):p.write_text(json.dumps(v,indent=2)+'\n')
def hy_task(arg):
 root,m=arg;r=Path(root)
 if (r/(m['symbol']+'-hy.json')).exists():return
 w=json.load(open(r/'window.json'));start,end=w['start_ns'],w['end_ns'];q=json.load(open(r/(m['symbol']+'-quotes.json')));out=[]
 source=[]
 events=list(map(json.loads,open(r/(m['symbol']+'-events.jsonl'))))
 audit=json.load(open(r/(m['symbol']+'-binance-quote-buy.json')))
 if not audit['config'].get('assume_tracked_word_id',False):
  seed=json.load(open(m['seed']));pool=seed['pools'][0];slot=pool.get('source_slot');word=seed['accounts'].get('0xe844701934d9c6085b292e428f41b911cc0b3872',{}).get('storage',{}).get(slot,'0x0');last_ms=(int(word,16)>>8)&((1<<56)-1);anchor=int(seed['anchor']['number'],16);aliases=set();queue=[]
  for e in events:
   if e['kind']!='oracle_candidate' or not e.get('block_number'):continue
   after=int(e['block_number'],16)>anchor
   if after:queue.append((e['mono_ns'],1,'candidate',e))
   if 'accepted_log_ns'in e:queue.append((max(e['mono_ns'],e['accepted_log_ns']),0,'learn',e))
  causal=[]
  for t,_,kind,e in sorted(queue,key=lambda z:(z[0],z[1])):
   writer=e['from'].lower()
   if kind=='learn':aliases.add(writer)
   if writer not in aliases or int(e['block_number'],16)<=anchor:continue
   stamp=(int(e['word'],16)>>8)&((1<<56)-1)
   if stamp<=last_ms:continue
   last_ms=stamp;causal.append(dict(e,mono_ns=t))
 else:causal=[e for e in events if e['kind']=='oracle_candidate']
 for e in causal:
  ns=w['origin_ns']+e['mono_ns']
  if not start<=ns<=end:continue
  raw=bytes.fromhex(e['word'][2:]);n=int.from_bytes(raw[:4],'big');price=(n&((1<<27)-1))*2**(n>>27)/1e8 if raw[4:6]!=b'\xff\xff' else float('nan');source.append(((ns-start)/1e6,price))
 for src in json.load(open(r/'sources.json')):
  if src['ticker']!=m['ticker']:continue
  bb=list(map(json.loads,open(r/(m['ticker']+'-'+src['venue']+'-bbo.jsonl'))));sides={}
  for side,i in [('bid',2),('ask',3),('provider_mid',None)]:
   x=[((b['recv_ns']-start)/1e6,float('nan') if b.get('invalid') else (float(b['bid'])+float(b['ask']))/2 if i is None else float(b[side])) for b in bb]
   y=source if i is None else [((z[0]-start)/1e6,float(z[i])/float(z[1]) if z[4] in ('priced','partial') and z[i] is not None else float('nan'))for z in q if start<=z[0]<=end]
   sides[side]=compare(x,y,start,end)
  out.append(dict(pool=m['pool'],ticker=m['ticker'],venue=src['venue'],sides=sides))
 save(r/(m['symbol']+'-hy.json'),out);print('hy done',m['symbol'],flush=True)

def metric(x,run):
 closed=sum((D(c['excess_vs_episode_hold_usdg'])for c in x.get('cycles',[])),D(0));turn=sum(float(c['open']['amount_usdg'])+float(c['close_amount_usdg'])for c in x.get('cycles',[]));err=run.get('statistics',{}).get('max_observed_price_error_bps',0)
 ages=[f['execution_source_age_ms'] for f in x['fills'] if f.get('execution_source_age_ms') is not None]
 return dict(side=x['entry_side'],open_bps=x['open_bps'],close_bps=x['close_bps'],cycles=len(x.get('cycles',[])),closed_usdg=float(closed),marked_usdg=float(x['excess_vs_hold_usdg']),open_episode=x.get('open_episode_at_end'),fills=len(x['fills']),rejects=len(x['rejections']),cancelled=x['cancelled'],max_swap_error_bps=err,closed_after_error_stress=float(closed)-turn*err/10000,closed_after_001_per_attempt=float(closed)-.01*(len(x['fills'])+len(x['rejections'])),closed_turnover=turn,valid=bool(run.get('truth_valid') and run.get('decision_valid')),execution_source_age_ms_quantiles=np.quantile(ages,[.5,.9,.99]).tolist() if ages else None)

def summarize(r):
 manifest=json.load(open(r/'manifest.json'));sources=json.load(open(r/'sources.json'));allrows=[];selected=[];replay=[];fixed=[];hy=[]
 for m in manifest:
  audit=json.load(open(r/(m['symbol']+'-binance-quote-buy.json')));run=audit.get('run',{});q=json.load(open(r/(m['symbol']+'-quotes.json')));replay.append(dict(pool=m['pool'],ticker=m['ticker'],truth_valid=run.get('truth_valid'),decision_valid=run.get('decision_valid'),statistics=run.get('statistics'),priced=sum(z[4]=='priced'for z in q),partial=sum(z[4]=='partial'for z in q),bid_priced=sum(z[2] is not None for z in q),ask_priced=sum(z[3] is not None for z in q),unavailable=sum(z[4]=='unavailable'for z in q),quote_errors=run.get('decision_quote_errors'),error=audit.get('error')))
  hp=r/(m['symbol']+'-hy.json')
  if hp.exists():hy+=json.load(open(hp))
  per=[]
  for src in sources:
   if src['ticker']!=m['ticker']:continue
   for seg in ('train','test'):
    for side in ('buy','sell'):
     p=r/f'{m["symbol"]}-{src["venue"]}-{seg}-{side}.json'
     if not p.exists():raise FileNotFoundError('Incomplete simulation: '+str(p))
     d=json.load(open(p));run=d.get('run',{})
     for result in run.get('results',[]):
      assert D(result['base_tokens'])>=0 and D(result['cash_usdg'])>=0
      for f in result['fills']:
       assert f['fill_ns']-f['signal_ns']==20_000_000
       amount=D(f['amount_usdg']);limit=D(f['limit_usdg'])
       assert amount<=limit if f['side']=='buy' else amount>=limit
     for x in run.get('results',[]):
      row=dict(pool=m['pool'],ticker=m['ticker'],venue=src['venue'],segment=seg,**metric(x,run));allrows.append(row);per.append(row)
      if seg=='test' and x['open_bps']=='10'and x['close_bps']=='-5':fixed.append(row)
  eligible=[x for x in per if x['segment']=='train'and x['valid']and x['cycles'] and x['closed_usdg']>0];chosen=max(eligible,key=lambda x:x['closed_usdg'])if eligible else None
  held=next((x for x in per if x['segment']=='test'and all(x[k]==chosen[k]for k in ('venue','side','open_bps','close_bps'))),None)if chosen else None
  selected.append(dict(ticker=m['ticker'],pool=m['pool'],training=chosen,test=held))
 save(r/'all-scenarios.json',allrows);save(r/'summary.json',dict(selected=selected,replay=replay,fixed_test=fixed,hy=hy))
 w=json.load(open(r/'window.json'));utc=lambda n:datetime.datetime.fromtimestamp(n/1e9,datetime.timezone.utc).isoformat(timespec='seconds');lines=['# Ohio replay / lead-lag / simulation', '',f"Window {utc(w['start_ns'])} to {utc(w['end_ns'])}. Chronological half split: {utc(w['split_ns'])}.",'','Actual Ohio application receipt timestamps; 20 ms signal-to-execution assumption. Fixed tokens initially worth 500 USDG, plus 500 USDG cash; extra inventory cap 500 USDG, sales limited to inventory. Buy-first and sell-first tested separately. Open 10/15/20/25/30 bps; opposite-side close -10/-5/0/5 bps, no holding-time exit. Source freshness limit 1 s; local full-provider expiry and size/fees applied.','', 'Gross price-taker research: no gas, failed-transaction costs, hedge funding/borrow, FX/issuer basis, signing/queue latency or persistent own-fill impact. Auxiliary calldata is assumed successful. Closed PnL is excess versus holding baseline for completed cycles; marked PnL can contain unclosed risk. Independent windows reset inventory. No live order submission.','', '## Replay quality','', '|Ticker|Pool|State valid|Swaps checked|Max price error bps|Bid / ask / total observations|','|---|---|---|---:|---:|---:|']
 for x in replay:
  st=x['statistics']or{};lines.append(f"|{x['ticker']}|{x['pool']}|{x['truth_valid'] and x['decision_valid']}|{st.get('observed_swap_count',0)}|{st.get('max_observed_price_error_bps',0):.4f}|{x['bid_priced']}/{x['ask_priced']}/{x['priced']+x['partial']+x['unavailable']}|")
 lines+=['','## Training-selected policy; subsequent test','', '|Ticker|Source / side / open / close|Train closed USDG|Test closed USDG|Test cycles|Test marked USDG|Test error-stressed USDG|','|---|---|---:|---:|---:|---:|---:|']
 for x in selected:
  a,b=x['training'],x['test']
  if not a or not b:lines.append(f"|{x['ticker']} {x['pool'][:10]}|No positive valid training policy|—|—|—|—|—|");continue
  lines.append(f"|{x['ticker']} {x['pool'][:10]}|{a['venue']} / {a['side']} / {a['open_bps']} / {a['close_bps']}|{a['closed_usdg']:.4f}|{b['closed_usdg']:.4f}|{b['cycles']}|{b['marked_usdg']:.4f}|{b['closed_after_error_stress']:.4f}|")
 benchmark=[x for x in allrows if x['segment']=='test' and x['open_bps']=='10' and x['close_bps']=='-10']
 save(r/'fixed-10-minus10-test.json',benchmark)
 lines+=['','## Fixed 10 / -10 bps held-out benchmark','','This is a fixed grid benchmark, not the training-selected cross-venue policy above. All original ETH source/side rows and every other nonzero-fill row are shown; remaining no-fill cases and all thresholds are in all-scenarios.json. Positive marked values with an open episode are not completed-cycle profits.','', '|Ticker/pool/source|Side|Cycles|Closed USDG|Marked USDG|Open episode|Error-stressed closed USDG|','|---|---|---:|---:|---:|---|---:|']
 for x in benchmark:
  if not (x['ticker']=='ETH' and x['pool'].startswith('0x1e8f')) and not x['fills']:continue
  lines.append(f"|{x['ticker']} {x['pool'][:10]}/{x['venue']}|{x['side']}|{x['cycles']}|{x['closed_usdg']:.4f}|{x['marked_usdg']:.4f}|{x['open_episode']}|{x['closed_after_error_stress']:.4f}|")
 lines+=['','## HY: exchange → pool','', 'Positive lag means exchange leads. Narrow ±100 ms and wider ±500 ms, 2 ms spacing from 1 ms plus zero/endpoints. Five chronological folds; positive fold count ignores insufficient-variation folds. HY contrast is not Pearson correlation. Provider-mid and executable-size bid/ask are distinct. Search-boundary or mixed-sign peaks are not precise exploitable delays. Fixed quote quantity is approximately 500 USDG at the first Binance ask.','', '|Ticker/pool/source|Bid peak ms|Ask peak ms|Provider mid ms|Bid positive/valid folds|Ask positive/valid folds|','|---|---:|---:|---:|---|---|']
 for h in hy:
  sides=h['sides'];peak=lambda s:sides[s].get('wide_all',{}).get('peak_ms','—')
  def folds(s):
   fs=[f for f in sides[s].get('wide_fold5',[])if f.get('status')=='ok'];return str(sum(f['peak_ms']>0 for f in fs))+'/'+str(len(fs))
  lines.append(f"|{h['ticker']} {h['pool'][:10]}/{h['venue']}|{peak('bid')}|{peak('ask')}|{peak('provider_mid')}|{folds('bid')}|{folds('ask')}|")
 lines+=['','## Exclusions','']
 for x in json.load(open(r/'excluded-pools.json')):lines.append(f"- {x['pool']}: {x['reason']}")
 iex=json.load(open(r/'iex-status.json'));lines.append('- IEX: '+str(sum(sum(x['counts'].values()) for x in iex))+' quotes in session at snapshot; no IEX backtest when no observations.')
 lines+=['','## State and execution limitations','','Writer bindings are learned only when matching pushed FeedUpdated logs arrive; subsequent qualified calldata updates are applied at ingress. A one-sided quote remains usable on that side, while provider reverts, extension reverts and partial fills remain unavailable at the requested size.','', 'For B89, the additional source reads two V3 pools. The scoped replay maintains pushed spot prices and observation timestamps/tick cumulatives, not V3 liquidity or seconds-per-liquidity cumulatives. Decision updates occur at actual log arrival; they are not backdated to Nitro ingress. Pyth still uses calldata. Auxiliary calldata is assumed successful, and extension state remains approximate. Inspect per-pool swap errors before interpreting simulation PnL.']
 lines+=['','Worst observed swap error stress is an illustrative per-leg turnover charge, not an error bound. Policies with invalid replay are excluded from selection. This after-hours sample does not establish regular-session performance. All individual scenarios, rejection diagnostics and provider ages are retained alongside this report.']
 (r/'RESULTS.md').write_text('\n'.join(lines)+'\n');print('\n'.join(lines[:35]))

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('stage',choices=['hy','summary']);p.add_argument('directory',type=Path);p.add_argument('--jobs',type=int,default=4);a=p.parse_args()
 if a.stage=='summary':summarize(a.directory)
 else:
  with concurrent.futures.ProcessPoolExecutor(max_workers=a.jobs) as ex:list(ex.map(hy_task,[(str(a.directory),m)for m in json.load(open(a.directory/'manifest.json'))]))
