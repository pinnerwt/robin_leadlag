"""One-time pinned initialization: canonical Uniswap V3, full bitmap + all ticks.
No requests after initialization. No partial tick coverage is promoted to complete.
"""
import argparse,json,time
from pathlib import Path
from decimal import Decimal
from bootstrap_state import Bootstrap,selector,word,unpack,signed
from bootstrap_batch import aggregate,split,merge
from v3_state import State,MIN_TICK,MAX_TICK
FACTORY='0x1f7d7550b1b028f7571e69a784071f0205fd2efa'
QUOTER='0x33e885ed0ec9bf04ecfb19341582aadcb4c8a9e7'
def data(sig,*args):return selector(sig)+''.join(word(int(x,16) if isinstance(x,str) and x.startswith('0x') else x).hex() for x in args)
def addr(n):return '0x'+word(n)[12:].hex()
def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--rpc-interval',type=float,default=1.1);parser.add_argument('--block',default='latest');parser.add_argument('--with-evm-state',action='store_true');parser.add_argument('--output',type=Path,default=Path('captures/amm-checkpoint.json'));args=parser.parse_args()
 cat=json.load(open('config/amm.json'));cfg=json.load(open('config/push.json'));meta={}
 for p in cfg['pools']:
  for i,t in enumerate(p['tokens']):meta[t.lower()]={'decimals':p['decimals'][i],'symbol':p.get('binance_symbol') if i==0 else None}
 chosen=[p for p in cat['pools'] if p['dex']=='uniswap-v3-robinhood' and p['metric_tokens_match']]
 b=Bootstrap('https://rpc-robinhood.blockmachine.io',interval=args.rpc_interval);head=b.rpc('eth_getBlockByNumber',[args.block,False]);block=head['number']
 seed={'schema':1,'anchor':head,'parent_header':head,'created_ns':time.time_ns(),'rpc_phase':'initialization_only','pools':[],'checks':[],'failed':[],'complete':False,'accounts':{},'execution_state_complete':False,'evm_dependency_coverage':'observed_getter_and_quote_paths_only'}
 def save():args.output.write_text(json.dumps(seed,indent=2)+'\n')
 def batch(calls):
  result=[]
  for start in range(0,len(calls),400):
   request=aggregate(calls[start:start+400]);rows=split(b.rpc('eth_call',[request,block]));assert len(rows)==len(calls[start:start+400]);result+=rows
   if args.with_evm_state:merge(seed,b.trace(request,block))
  return result
 print('anchor',block,'pools',len(chosen),flush=True);save()
 sigs=['token0()','token1()','fee()','tickSpacing()','liquidity()','slot0()','factory()']
 values=batch([{'to':p['pool'],'data':data(sig)} for p in chosen for sig in sigs])
 for i,p in enumerate(chosen):
  try:
   rows=values[i*7:(i+1)*7];assert all(ok for ok,_ in rows),'metadata reverted';vals=[unpack(d) for _,d in rows]
   assert addr(vals[6][0])==FACTORY,'noncanonical factory'
   tokens=[addr(vals[j][0]) for j in (0,1)];assert set(tokens)==set(p['tokens']),'token address mismatch'
   slot=vals[5];fee=vals[2][0];spacing=signed(vals[3][0]);assert spacing>0 and fee<1000000 and slot[6]==1
   quote=next((t for t in ['0x5fc5360d0400a0fd4f2af552add042d716f1d168','0x0bd7d308f8e1639fab988df18a8011f41eacad73'] if t in tokens),tokens[1]);base=next(t for t in tokens if t!=quote)
   row=dict(p,tokens=tokens,base_token=base,quote_token=quote,base_index=tokens.index(base),decimals=[meta[t]['decimals'] for t in tokens],binance_symbol=meta[base]['symbol'],fee=fee,spacing=spacing,sqrt=str(slot[0]),tick=signed(slot[1]),liquidity=str(vals[4][0]),bitmap={},ticks={},full_tick_coverage=False)
   seed['pools'].append(row)
  except Exception as e:seed['failed'].append({'pool':p['pool'],'reason':str(e)})
 save()
 jobs=[(p,w) for p in seed['pools'] for w in range((MIN_TICK//p['spacing'])>>8,((MAX_TICK//p['spacing'])>>8)+1)]
 rows=batch([{'to':p['pool'],'data':data('tickBitmap(int16)',w)} for p,w in jobs])
 for (p,w),(ok,d) in zip(jobs,rows):
  if not ok:raise ValueError('bitmap missing')
  p['bitmap'][str(w)]=str(unpack(d)[0])
 save();print('bitmap words',len(jobs),flush=True)
 jobs=[]
 for p in seed['pools']:
  for w,mask in p['bitmap'].items():
   mask=int(mask)
   while mask:
    bit=(mask&-mask).bit_length()-1;t=((int(w)<<8)+bit)*p['spacing'];jobs.append((p,t));mask&=mask-1
 rows=batch([{'to':p['pool'],'data':data('ticks(int24)',t)} for p,t in jobs])
 for (p,t),(ok,d) in zip(jobs,rows):
  if not ok:raise ValueError('tick missing')
  vals=unpack(d);assert vals[0]>0 and vals[7]==1;p['ticks'][str(t)]=[str(vals[0]),str(signed(vals[1]))]
 for p in seed['pools']:
  assert sum(int(v[1]) for v in p['ticks'].values())==0,'net liquidity sum'
  assert sum(int(v[1]) for t,v in p['ticks'].items() if int(t)<=p['tick'])==int(p['liquidity']),'active liquidity mismatch'
  p['full_tick_coverage']=True
 save();print('initialized ticks',len(jobs),flush=True)
 jobs=[]
 for p in seed['pools']:
  state=State.load(p);base=p['base_index']
  for size in ['0.02','0.1']:
   amount=int(Decimal(size)*10**p['decimals'][base])
   for sell in [True,False]:
    tokenin=p['base_token'] if sell else p['quote_token'];tokenout=p['quote_token'] if sell else p['base_token'];zero=tokenin==p['tokens'][0]
    fn='quoteExactInputSingle' if sell else 'quoteExactOutputSingle'
    local=state.swap(zero,amount if sell else -amount)
    jobs.append((p,size,sell,local,{'to':QUOTER,'data':data(fn+'((address,address,uint256,uint24,uint160))',tokenin,tokenout,amount,p['fee'],0)}))
 outputs=batch([j[-1] for j in jobs])
 for (p,size,sell,local,_),(ok,d) in zip(jobs,outputs):
  values=unpack(d) if ok else [];quote_index=1-p['base_index'];expected=abs(local['amount'+str(quote_index)])
  match=ok and values[0]==expected and values[1]==local['sqrt'] and local['unfilled']==0
  seed['checks'].append(dict(pool=p['pool'],size_tokens=size,side='bid' if sell else 'ask',matched=match,local_amount=str(expected),remote_amount=str(values[0]) if ok else None))
 confirmed=b.rpc('eth_getBlockByNumber',[block,False])
 if confirmed['hash']!=head['hash']:raise ValueError('snapshot anchor changed during bootstrap')
 seed['complete']=not seed['failed'] and all(c['matched'] for c in seed['checks']);seed['quote_state_complete']=seed['complete'];seed['rpc_calls']=b.calls;save()
 print('complete',seed['complete'],'checks',len(seed['checks']),'matched',sum(c['matched'] for c in seed['checks']),'calls',b.calls,flush=True)
 if not seed['complete']:raise SystemExit(1)
if __name__=='__main__':main()
