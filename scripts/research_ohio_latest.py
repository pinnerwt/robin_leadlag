"""Reproducible offline pool-keyed replay, HY and chronological threshold research."""
import argparse,collections,concurrent.futures,hashlib,json,math,subprocess
from pathlib import Path
from decimal import Decimal as D,ROUND_FLOOR
import causal_spcx_backtest as bt

def save(p,v):p.write_text(json.dumps(v,indent=2)+'\n')
def prepare(c,r):
 from bootstrap_state import mapping,selector
 manifest=json.load(open(c/'manifest.json'))
 for name,meta in manifest['files'].items():
  p=c/name;h=hashlib.file_digest(p.open('rb'),'sha256').hexdigest();assert p.stat().st_size==meta['size'] and h==meta['sha256'],name
 save(r/'integrity.json',dict(files=len(manifest['files']),all_sha256_match=True))
 status=json.load(open(c/'robinhood-status.json'));rec=status['recovery'];assert rec['generation']==0 and rec['replay_ready'] and len(rec['intervals'])==1 and rec['intervals'][0]['end_mono_ns'] is None
 seed=json.load(open(c/Path(rec['checkpoint']['path']).name));save(r/'checkpoint.json',seed)
 rows=[];excluded=[]
 for pool in seed['pools']:
  p=dict(pool);ticker='ETH' if p['binance_symbol']=='ETHUSDT' else p['binance_symbol'].removesuffix('BUSDT');stem=ticker+'-'+p['pool'][2:10].lower()
  if not p.get('source'):
   signatures=['offchainOracle()','baseFeedId()','quoteFeedId()','source()']
   calls=[dict(to=p['provider'],data=selector(sig),tx=sig) for sig in signatures]
   proc=subprocess.run(['target/release/examples/check_calls',str(r/'checkpoint.json')],input=''.join(json.dumps(x)+'\n' for x in calls),text=True,capture_output=True,check=True)
   getters={x['tx']:x for x in map(json.loads,proc.stdout.splitlines())};save(r/(stem+'-getters.json'),getters)
   values={k:int(v['output'],16) for k,v in getters.items() if v.get('success')}
   if len(values)==4 and values['offchainOracle()']==int('30a88bf894d1b806125a23ebf23d715496fd7102',16) and values['quoteFeedId()']==0 and values['source()'] in (0,int('ed4d8229a521cfdbc42a4b548b443999dc29b93a',16)):
    feed_id=values['baseFeedId()'];slot=mapping(feed_id,1);assert slot in seed['accounts']['0x30a88bf894d1b806125a23ebf23d715496fd7102']['storage']
    p.update(source_slot='0x0',aux_feed_id=feed_id)
    dependency={}
    if values['source()']:
     # This scoped projection is tied to the inspected deployed adapter. A new
     # implementation needs a fresh dependency/read audit, not blind reuse.
     for addr,expected in [('0xed4d8229a521cfdbc42a4b548b443999dc29b93a','104a6a8e0f896e20e1dc5b38cca667037cb7c13ed7f9bdd7c06f809ba135caca'),('0x0a17a5cb7fe00ed0615be8e2fb8658b02b81e490','84f80a76d16850904cc3656a17b78717d97c68e3c86c0199571eb529f26add62')]:
      assert hashlib.sha256(bytes.fromhex(seed['accounts'][addr]['code'][2:])).hexdigest()==expected,'B89 adapter bytecode changed'
     dependency=dict(v3_price_pools=['0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca','0x69bfaf19c9f377bb306a89aed9f6b07e2c1a8d9a'],v3_projection='spot_and_observation_tick_history');p.update(dependency)
    path=r/(stem+'-seed.json');save(path,dict(seed,pools=[p]));rows.append(dict(symbol=stem,reference_symbol=p['binance_symbol'],ticker=ticker,pool=p['pool'].lower(),seed=str(path),**dependency));continue
   excluded.append(dict(ticker=ticker,pool=p['pool'],provider=p['provider'],reason='Additional nonzero or unsupported provider source; transition coverage is not implemented. See local getter evidence.'));continue
  key=int(mapping(int(p['pool'],16),3),16)+1;feed=seed['accounts'][p['source'].lower()]['storage']['0x'+format(key,'064x')];assert feed.startswith('0x8dfdc825') and feed.endswith('00')
  ident=(int(feed,16)>>8)&255;slot=feed[:42]+format(ident,'024x');assert slot in seed['accounts']['0xe844701934d9c6085b292e428f41b911cc0b3872']['storage']
  p.update(source_slot=slot,feed_topic=feed,word_id=ident)
  path=r/(stem+'-seed.json');save(path,dict(seed,pools=[p]));rows.append(dict(symbol=stem,reference_symbol=p['binance_symbol'],ticker=ticker,pool=p['pool'].lower(),feed_topic=feed,word_id=ident,source_slot=slot,seed=str(path)))
 save(r/'manifest.json',rows);save(r/'excluded-pools.json',excluded)
 with open(r/'extraction.log','w') as log:
  dec=subprocess.Popen(['zstd','-q','-dc',str(c/'robinhood.bin.zst')],stdout=subprocess.PIPE)
  run=subprocess.run(['target/release/examples/prepare_recovery_causal',str(r)],stdin=dec.stdout,stderr=log);dec.stdout.close();assert dec.wait()==0 and run.returncode==0
 failures=json.load(open(r/'extraction-audit.json'));assert not failures,failures[:3]
 session=next(x for x in map(json.loads,open(r/(rows[0]['symbol']+'-events.jsonl'))) if x['kind']=='session');origin=session['start_utc_ns']
 # End before the frozen tape tail; never infer coverage from the requested cutoff alone.
 chain=json.load(open(c/'robinhood.bin.zst.json'));eqmeta=json.load(open(next(c.glob('ohio-equity-*.bin.zst.json'))))
 end=min(chain['last_recv_ns']['nitro_push'],chain['last_recv_ns']['chain_log'],eqmeta['last_recv_ns']['equity_bbo'])-2_000_000_000
 start=max(origin+rec['checkpoint']['available_mono_ns'],seed['finished_ns'])+1_000_000_000
 w=dict(origin_ns=origin,start_ns=start,end_ns=end,split_ns=start+(end-start)//2);save(r/'window.json',w)
 from ohio_spot_hy import load_equities
 series,quality=load_equities(sorted(c.glob('ohio-equity-*.bin.zst')),start,end);save(r/'bbo-quality.json',quality)
 catalog=[]
 for venue,ticker,side in sorted(series):
  if side!='bid':continue
  bid=series[(venue,ticker,'bid')];ask=series[(venue,ticker,'ask')];assert len(bid)==len(ask)
  out=[]
  for (t,b),(ta,a) in zip(bid,ask):
   assert t==ta;ns=start+round(t*1e6)
   if not start<=ns<=end:continue
   out.append(dict(recv_ns=ns,mono_ns=ns-origin,invalid=True) if not math.isfinite(b) or not math.isfinite(a) else dict(recv_ns=ns,mono_ns=ns-origin,bid=str(b),ask=str(a)))
  if len(out)<10:continue
  p=r/(ticker+'-'+venue+'-bbo.jsonl');p.write_text(''.join(json.dumps(x)+'\n' for x in out));catalog.append(dict(ticker=ticker,venue=venue,count=len(out)))
 save(r/'sources.json',catalog);save(r/'iex-status.json',manifest['iex_status']);print('prepared',w,'pools',len(rows),'sources',len(catalog),flush=True)

def config(r,row,baseline,start):
 c=json.load(open('config/spcx-ohio-translated-backtest.json'))
 for k in ('initial_mark_price_usdg','initial_position_tokens'):c.pop(k,None)
 origin=json.load(open(r/'window.json'))['origin_ns']
 c.update(assume_tracked_word_id=False,binding_assumption='Recovered writer plus causally learned feed binding; unknown writers wait for their first matching pushed log',checkpoint=row['seed'],symbol=row['reference_symbol'],provider_mode='provider-full',fixed_baseline=True,initial_position_tokens=baseline,hy_fixed_quantity=baseline,initial_inventory_usdg='0',initial_cash_usdg='500',warmup_seconds=(start-origin)/1e9,return_invalid_diagnostics=True,cache_no_order=True,diagnostic_probes=False,share_candidate_evaluations=True,open_close_grid=[dict(open_bps=str(o),close_bps=str(cl))for o in (10,15,20,25,30)for cl in (-10,-5,0,5)])
 c['routes']=[dict(name='ohio_receipt_exec20',chain_shift_ms=0,truth_chain_shift_ms=0,binance_shift_ms=0,execution_ms=20)];c['route_assumptions']='Actual Ohio receipt times, 20 ms execution; no Taiwan translation.'
 return c

def task(arg):
 root,row,venue,segment,side=arg;r=Path(root);w=json.load(open(r/'window.json'));start=w['start_ns'] if segment in ('train','quote') else w['split_ns'];end=w['split_ns']-1 if segment=='train' else w['end_ns'];tag=f'{row["symbol"]}-{venue}-{segment}-{side}';path=r/(tag+'.json')
 if path.exists():return
 bb=[x for x in map(json.loads,open(r/(row['ticker']+'-'+venue+'-bbo.jsonl'))) if start<=x['recv_ns']<=end]
 if not any(not x.get('invalid') for x in bb):return
 if segment=='quote':bb=[bb[0],bb[-1]]  # Reference-independent state-update/timer sampling.
 # Identical token baseline across venues, windows and both sides for a pool.
 first=next(x for x in map(json.loads,open(r/(row['ticker']+'-binance-bbo.jsonl'))) if not x.get('invalid'))
 baseline=str((D(500)/D(first['ask'])).quantize(D('1e-18'),rounding=ROUND_FLOOR));c=config(r,row,baseline,start);c['entry_side']=side;c['quote_only']=segment=='quote'
 events=[x for x in map(json.loads,open(r/(row['symbol']+'-events.jsonl'))) if x.get('mono_ns',0)<=end-w['origin_ns']]
 print('start',tag,len(events),len(bb),flush=True);out=dict(pool=row['pool'],ticker=row['ticker'],venue=venue,segment=segment,side=side,config=c);quotes=[]
 def observe(ns,q,v):quotes.append([ns,str(q),v.get('bid_usdg'),v.get('ask_usdg'),v['status'],v.get('reason')])
 try:out['run']=bt.run(c,c['routes'][0],events,bb,pool_observer=observe if segment=='quote' else None)
 except Exception as e:out['error']=repr(e)
 save(path,out)
 if segment=='quote':save(r/(row['symbol']+'-quotes.json'),quotes)
 run=out.get('run',{});print('done',tag,run.get('truth_valid'),run.get('decision_valid'),out.get('error'),flush=True)

def run(r,stage,jobs):
 rows=json.load(open(r/'manifest.json'));sources=json.load(open(r/'sources.json'));tasks=[]
 for row in rows:
  if stage=='quote':tasks.append((str(r),row,'binance','quote','buy'));continue
  for src in sources:
   if src['ticker']==row['ticker']:
    for seg in ('train','test'):
     for side in ('buy','sell'):tasks.append((str(r),row,src['venue'],seg,side))
 tasks.sort(key=lambda t:(t[1]['ticker']=='ETH',t[1]['symbol'],t[2],t[3],t[4]))
 with concurrent.futures.ProcessPoolExecutor(max_workers=jobs) as ex:list(ex.map(task,tasks))

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('stage',choices=['prepare','quote','simulation']);p.add_argument('directory',type=Path);p.add_argument('--capture',type=Path);p.add_argument('--jobs',type=int,default=4);a=p.parse_args();a.directory.mkdir(parents=True,exist_ok=True)
 if a.stage=='prepare':prepare(a.capture,a.directory)
 else:run(a.directory,a.stage,a.jobs)
