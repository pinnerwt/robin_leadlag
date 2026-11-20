"""One-shot, pinned-block state seed. Run only after push capture is established.
No periodic calls or runtime fallback. Every read stays at the same block.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from decimal import Decimal
from functools import lru_cache
import json
from pathlib import Path
import subprocess
import threading
import time
import urllib.request
import urllib.error

@lru_cache(None)
def hashhex(data):return subprocess.check_output(['cast','keccak'],input='0x'+data.hex()+'\n',text=True).strip()
@lru_cache(None)
def selector(signature):return subprocess.check_output(['cast','sig',signature],text=True).strip()
def word(x):return (x%(1<<256)).to_bytes(32,'big')
def mapping(key,slot):return hashhex(word(key)+word(slot))
def unpack(data):return [int(data[i:i+64],16) for i in range(2,len(data),64)]
def signed(x,bits=256):return x-(1<<bits) if x>>(bits-1) else x

def simulate(pool,zero_for_one,amount,prices):
    # Buy exact token0 output (negative); sell exact token0 input (positive).
    limit=1 if zero_for_one else (1<<128)-1
    args=[0,0,int(zero_for_one),amount,limit,*prices,9*32]
    data='0x658b6cb7'+b''.join(word(v) for v in args).hex()+word(0).hex()
    return {'to':pool,'from':'0x'+'00'*20,'data':data,'gas':'0x1c9c380'}

class Bootstrap:
    def __init__(self,url,interval=1.1):
        if interval<0.05:raise ValueError("initialization request interval too small")
        self.url=url;self.interval=interval;self.calls=0;self.lock=threading.Lock();self.next_request=0
    def rpc(self,method,params):
        with self.lock:
            delay=max(0,self.next_request-time.monotonic())
            time.sleep(delay);self.next_request=time.monotonic()+self.interval;self.calls+=1
        req=urllib.request.Request(self.url,data=json.dumps(dict(jsonrpc='2.0',id=1,method=method,params=params)).encode(),headers={'Content-Type':'application/json','User-Agent':'robin-leadlag/0.1'})
        for attempt in range(6):
            try:
                with urllib.request.urlopen(req,timeout=45) as response:r=json.load(response)
                break
            except urllib.error.HTTPError as error:
                if error.code not in (429,502,503,504) or attempt==5:raise
                time.sleep(min(30,2**(attempt+1)))
        if 'error' in r:raise RuntimeError(json.dumps(r['error']))
        return r['result']
    def trace(self,call,block):return self.rpc('debug_traceCall',[call,block,{'tracer':'prestateTracer'}])
    def one_pool(self,row,block,sizes):
        address=row['pool'].lower();call=lambda data:{'to':address,'data':data,'gas':'0x1c9c380'}
        imm=self.rpc('eth_call',[call('0xbcdb4dad'),block]);w=unpack(imm)
        if len(w)!=24:raise ValueError('unsupported immutable layout')
        lower,upper=map(signed,w[9:11])
        if not 0<=upper-lower<2048:raise ValueError('invalid bin range')
        # Fixed slots, every bin state AND every bin's total shares (stop-loss depends on shares).
        slots=[word(i).hex() for i in range(4)]
        for i in range(lower,upper+1):
            slots.extend([mapping(i,4)[2:],mapping(i,5)[2:]])
        data='0xdbd035ff'+word(32).hex()+word(len(slots)).hex()+''.join(slots)
        storage_result=self.rpc('eth_call',[call(data),block]);values=unpack(storage_result)[2:]
        if len(values)!=len(slots):raise ValueError('extsload length')
        traces=[self.trace(call(data),block)]
        provider='0x'+word(w[8] or values[3])[-20:].hex()
        getquote={'to':provider,'data':'0x171755b1','gas':'0x1c9c380'}
        quote_trace=self.rpc('debug_traceCall',[getquote,block,{'tracer':'callTracer'}])
        traces.append(self.trace(getquote,block))
        record=dict(row);record.update(immutables=imm,provider=provider,storage=dict(zip(('0x'+s for s in slots),('0x'+word(v).hex() for v in values))),quote_trace=quote_trace,quote_checks=[])
        if not quote_trace.get('error') and len(quote_trace.get('output',''))==194:
            prices=unpack(quote_trace['output'])
            for size in list(dict.fromkeys([*sizes,"1000000"])):
                raw=Decimal(size)*10**row['decimals'][0]
                if raw!=int(raw) or not 0<raw<1<<127:raise ValueError('invalid token size')
                for sell in [True,False]:
                    request=simulate(address,sell,int(raw) if sell else -int(raw),prices)
                    check=self.rpc('debug_traceCall',[request,block,{'tracer':'callTracer'}])
                    traces.append(self.trace(request,block))
                    record['quote_checks'].append(dict(seed_only=size not in sizes,size_tokens=size,side='bid' if sell else 'ask',call=request,expected=check.get('output'),error=check.get('error')))
        return record,traces

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',type=Path,default=Path('config/push.json'))
    p.add_argument('--rpc',default='https://rpc-robinhood.blockmachine.io')
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--sizes',default='0.02,0.1')
    p.add_argument('--limit',type=int)
    p.add_argument('--block',help='optional recorded head number; no latest moving target')
    a=p.parse_args();b=Bootstrap(a.rpc)
    head=b.rpc('eth_getBlockByNumber',[a.block or 'latest',False]);block=head['number']
    config=json.loads(a.config.read_text());rows=config['pools'][:a.limit]
    # Preserve the selected anchor immediately, even if a pool fails.
    state=dict(version=1,anchor=head,created_ns=time.time_ns(),accounts={},pools=[],failed=[],rpc_phase='bootstrap_only',storage_complete=False)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    print('anchor',block,head['hash'],flush=True)
    def merge(accounts):
        for address,account in accounts.items():
            dst=state['accounts'].setdefault(address,{})
            for k,v in account.items():
                if k=='storage':
                    storage=dst.setdefault(k,{})
                    for slot,value in v.items():
                        if slot in storage and storage[slot]!=value:raise ValueError('inconsistent fixed-block slot')
                        storage[slot]=value
                else:
                    if k in dst and dst[k]!=v:raise ValueError('inconsistent fixed-block account')
                    dst[k]=v
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures={executor.submit(b.one_pool,row,block,a.sizes.split(',')):row for row in rows}
        for future in as_completed(futures):
            row=futures[future]
            try:
                record,traces=future.result()
                for trace in traces:merge(trace)
                merge({record['pool'].lower():{'storage':record['storage']}})
                state['pools'].append(record)
                print('seeded',row['pair'],row['pool'],len(record['quote_checks']),flush=True)
            except Exception as e:
                state['failed'].append(dict(pool=row['pool'],reason=str(e)))
                print('failed',row['pair'],str(e)[:180],flush=True)
    a.output.with_suffix('.unverified.json').write_text(json.dumps(state,separators=(',',':')))
    verified=b.rpc('eth_getBlockByNumber',[block,False])
    if verified['hash']!=head['hash']:raise ValueError('anchor reorg')
    state.update(rpc_calls=b.calls,finished_ns=time.time_ns(),anchor_verified=True)
    temp=a.output.with_suffix('.tmp');temp.write_text(json.dumps(state,separators=(',',':')));temp.replace(a.output)
    print('complete',len(state['pools']),'failed',len(state['failed']),'accounts',len(state['accounts']),'calls',b.calls,flush=True)

if __name__=='__main__':main()
