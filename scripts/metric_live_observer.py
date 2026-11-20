"""B89 live state observer. Cold RPC checkpoint, then pushed calldata/logs only.
Confirmed logs reduce an ordered state; speculative Pyth calldata affects a copy.
Missing transactions, reorgs, unknown slots, and stream gaps invalidate the epoch.
"""
import argparse, asyncio, collections, json, struct, subprocess, sys, time
from decimal import Decimal
from pathlib import Path
import websockets
from tape import MAGIC, encode, decode
from v3_feed_overlay import build as build_overlay, parse_swap

POOL='0xb89fd35ebc48b791339520af812b70f71d823cc5'
PYTH='0x30a88bf894d1b806125a23ebf23d715496fd7102'
FEED='0x29e088dffd7bf6815d088137a59f364d6747163baa7ff4bc47f316a1ad1b9586'
SWAP='0xc42079f94a6350d7e6235f29174924f928cc2ac818eb64fed8004e115fbcca67'
V3_TOPICS={'0xc42079f94a6350d7e6235f29174924f928cc2ac818eb64fed8004e115fbcca67','0x7a53080ba414158be7ec69b987b5fb7d07dee101fe85488f0853ae16239d0bde','0x0c396cd989a39f4459b5fa1aed6a9a8dcdbc45908acfd67e028cd568da98982c','0xac49e518f90a358f652e4400164f05a5d8f7e35e7747279bc3a93dbf584e125a'}

def save(path, value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(value,indent=2)+'\n');tmp.replace(path)

class Worker:
    def __init__(self):
        self.p=subprocess.Popen(['target/release/metric-live-state','--provider-full'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True,bufsize=1)
    def call(self, **r):
        self.p.stdin.write(json.dumps(r,separators=(',',':'))+'\n');self.p.stdin.flush()
        line=self.p.stdout.readline()
        if not line:raise RuntimeError('state worker exited')
        response=json.loads(line)
        if 'error' in response:raise ValueError(response['error'])
        return response['result']
    def close(self):
        self.p.terminate()
        try:self.p.wait(timeout=5)
        except subprocess.TimeoutExpired:self.p.kill();self.p.wait()

class Projection:
    def __init__(self, worker):
        self.worker=worker;self.heads={};self.metadata={};self.transactions={};self.pending={}
        self.sequence=None;self.anchor=None;self.logs=collections.deque();self.last_log=None
        # Optional calldata-first V3 spot overlays (pool -> v3_feed_overlay.Overlay); logs remain the confirmed state.
        self.overlays={};self.overlay_on=True;self.order=0;self.v3_sqrt={};self.v3_check_wanted=False;self.v3_check_queue=None
        self.header=None;self.last_nitro=0;self.last_head=0;self.version=0;self.counts=collections.Counter()
        self.effects=collections.deque();self.timings=collections.deque();self.wallet=None;self.executor=None;self.audit_queue=None;self.audit_interval_ns=60_000_000_000;self.next_audit_ns=0;self.audit_sizes=[str(10**15),str(58*10**15),str(10**17)];self.audit_local_error=None;self.log_blocks=set();self.unlogged_heads={};self.v3=set();self.seed_hash=None;self.anchor_seen=False;self.last_flush=0
    def initialize(self, seed):
        self.worker.call(kind='initialize',seed=seed)
        self.anchor=int(seed['anchor']['number'],16);self.seed_hash=seed['anchor']['hash']
        self.header=seed['anchor'].copy();self.v3=set(seed['pools'][0]['v3_price_pools'])
    def update(self, kind, value, stamp):
        if kind=='head':
            n=int(value['number'],16);h=value['hash']
            if self.heads:
                previous=list(self.heads.values())[-1]
                if n!=int(previous['number'],16)+1 or value['parentHash']!=previous['hash']:
                    raise ValueError('head discontinuity')
            self.heads[h]=value;self.last_head=stamp
            if (self.anchor is None or n>self.anchor) and int(value.get('logsBloom','0x0'),16) and h not in self.log_blocks:self.unlogged_heads[h]=stamp
            if self.anchor==n:
                if h!=self.seed_hash:raise ValueError('checkpoint fork')
                self.anchor_seen=True
        elif kind=='nitro':
            messages=value.get('messages',[])
            for m in messages:
                seq=m['sequenceNumber']
                if self.sequence is not None and seq<=self.sequence:
                    continue
                if self.sequence is not None and seq!=self.sequence+1:raise ValueError('Nitro sequence gap')
                self.sequence=seq;self.last_nitro=stamp
                h=m['blockHash'];header=m['message']['message']['header']
                self.metadata[h]={'timestamp':hex(header['timestamp']),'l1BlockNumber':hex(header['blockNumber'])}
                row={'payload':{'messages':[m]},'recv_ns':stamp,'mono_ns':stamp}
                txs=self.worker.call(kind='decode',row=row)['transactions']
                for t in txs:
                    if 'tx' not in t:
                        if t.get('system_kind')!='batch_posting_report_v2':raise ValueError('unidentified Nitro transaction')
                        self.counts['batch_reports']+=1;continue
                    tx=t['tx'];self.transactions[tx]=t
                    self.order+=1;t['order']=self.order
                    for overlay in self.overlays.values():overlay.feed_tx(tx,t.get('to'),t.get('data'),self.order)
                    if self.executor and (t.get('to') or '').lower()==self.executor:
                        self.timings.append(dict(kind='feed_seen',tx=tx,received_ns=stamp,block_hash=h,sequence=seq))
                    if (t.get('to') or '').lower()==PYTH:
                        req={'kind':'aux_oracle','transaction':{'to':PYTH,'data':t['data']}}
                        self.pending[tx]=(req,h,stamp)
                        self.counts['provider_calldata']+=1
                self.version+=1
        elif kind=='log':
            if value.get('removed'):raise ValueError('removed log')
            value=dict(value,arrival_ns=stamp)
            self.log_blocks.add(value['blockHash']);self.unlogged_heads.pop(value['blockHash'],None)
            cursor=tuple(int(value[k],16) for k in ('blockNumber','transactionIndex','logIndex'))
            if self.last_log is not None and cursor<=self.last_log:raise ValueError('log stream reordered or duplicated')
            self.last_log=cursor
            if self.anchor is not None and cursor[0]>self.anchor:
                self.logs.append(value)
                if self.overlays:
                    # Any log proves the stream passed earlier transactions; a pool's own
                    # Swap log is its new base. Surprises get a background pinned RPC check.
                    t=self.transactions.get(value['transactionHash']);own=self.swap_pool(value)
                    for pool,overlay in self.overlays.items():
                        if overlay.log(t['order'] if t else None,value if pool==own else None,t.get('to') if t else None):self.v3_check_wanted=True
        self.drain()
        # Bound history; unknown old references cause recovery rather than guessing.
        if len(self.heads)>6000:
            old=list(self.heads)[:1000]
            for h in old:self.heads.pop(h);self.metadata.pop(h,None);self.log_blocks.discard(h);self.unlogged_heads.pop(h,None)
            self.transactions={k:t for k,t in self.transactions.items() if t['block_hash'] in self.heads or t['block_hash'] in self.metadata}
        if len(self.logs)>100000 or len(self.pending)>10000:raise ValueError('projection backlog exceeded')
    def drain(self):
        if self.anchor is None:return
        # A later transaction on the ordered all-logs subscription is the barrier
        # for completeness of the preceding transaction. Headers alone are not.
        while self.logs:
            tx=self.logs[0]['transactionHash'];group=[]
            for log in self.logs:
                if log['transactionHash']!=tx:break
                group.append(log)
            else:return
            h=group[0]['blockHash']
            if h not in self.metadata or h not in self.heads:return
            if self.heads[h]['number']!=group[0]['blockNumber']:raise ValueError('log branch mismatch')
            header=self.metadata[h]
            pool_logs=[]
            for log in group:
                address=log['address'].lower();topic=log['topics'][0] if log['topics'] else ''
                if address==PYTH and topic==FEED:
                    if tx not in self.transactions:raise ValueError('accepted oracle missing calldata')
                    t=self.transactions[tx]
                    if (t.get('to') or '').lower()!=PYTH:raise ValueError('indirect oracle update unsupported')
                    self.worker.call(kind='confirmed',request={'kind':'aux_oracle','transaction':{'to':PYTH,'data':t['data']}})
                    self.pending.pop(tx,None);self.counts['provider_confirmed']+=1
                elif address in self.v3 and topic in V3_TOPICS:
                    log=dict(log,blockTimestamp=header['timestamp'])
                    self.worker.call(kind='confirmed',request={'kind':'v3_price','log':log})
                    if address in self.overlays and topic==SWAP:self.v3_sqrt[address]=parse_swap(log)['sqrt']
                    self.counts['v3_updates']+=1
                elif address==POOL:
                    pool_logs.append(log)
                    if topic=='0xcad09799f755048f0fd388c6b2fcc8e0cebefd15756c6903522cc2a95f661f70':continue
                    response=self.worker.call(kind='confirmed',request={'kind':'pool','logs':pool_logs,'header':header})
                    d=response['update']['diagnostic']
                    if d['max_price_error_bps']>2:raise ValueError('swap projection drift exceeds 2 bps')
                    self.counts['swaps']+=d['swap_count']
                    self.counts['max_swap_error_bps']=max(self.counts['max_swap_error_bps'],d['max_price_error_bps'])
                    self.counts['pool_updates']+=1
                    pool_logs=[]
            if pool_logs:raise ValueError('incomplete swap log group')
            self.header={k:hex(max(int(self.header[k],16),int(header[k],16))) for k in ('timestamp','l1BlockNumber')}
            self.last_flush=int(group[0]['blockNumber'],16)
            if self.executor and any(l['address'].lower()==self.executor for l in group):
                self.effects.append(dict(kind='receipt',receipt=dict(transactionHash=tx,blockHash=h,blockNumber=group[0]['blockNumber'],status='0x1',**{'from':self.wallet,'to':self.executor},logs=group,_source='push_logs',_observed_ns=max(l.get('arrival_ns',0) for l in group))))
            for _ in group:self.logs.popleft()
            if self.v3_check_wanted and len(self.v3_sqrt)==len(self.overlays) and self.logs and self.logs[0]['blockNumber']!=group[0]['blockNumber'] and self.v3_check_queue is not None and self.v3_check_queue.empty():
                # Block complete: its end-of-block pool price is what a pinned slot0 read must return.
                self.v3_check_queue.put_nowait(dict(number=group[0]['blockNumber'],hash=h,sqrt=dict(self.v3_sqrt)));self.v3_check_wanted=not self.overlay_on
            if self.audit_queue is not None and self.logs and self.logs[0]['blockNumber']!=group[0]['blockNumber'] and time.time_ns()>=self.next_audit_ns and self.audit_queue.empty():
                try:
                    local=self.worker.call(kind='audit',header=header,sizes=self.audit_sizes)
                    self.audit_queue.put_nowait(dict(number=group[0]['blockNumber'],hash=h,local=local))
                    self.audit_local_error=None
                except ValueError as exc:self.audit_local_error=str(exc)
                self.next_audit_ns=time.time_ns()+self.audit_interval_ns
            self.version+=1
            # A log barrier beyond a transaction proves its unaccepted update is
            # behind the confirmed log frontier; remove it from speculation.
            for tx2,(_,h2,_) in list(self.pending.items()):
                if h2 in self.heads and int(self.heads[h2]['number'],16)<self.last_flush:
                    self.pending.pop(tx2);self.counts['unaccepted_overlay_expired']+=1
    def check_progress(self,now,timeout_ns):
        if now-min(self.last_head,self.last_nitro)>timeout_ns:raise RuntimeError('pushed data stalled; recovering checkpoint')
        if self.unlogged_heads and now-min(self.unlogged_heads.values())>timeout_ns:raise RuntimeError('logs subscription stalled despite nonempty blocks')
    def quote(self, raw, now):
        if not self.anchor_seen:raise ValueError('checkpoint not joined to pushed heads')
        if now-min(self.last_head,self.last_nitro)>2_000_000_000:raise ValueError('stale pushed stream')
        # Do not quote past any unprocessed relevant log or unknown metadata.
        overlays=self.overlays if self.overlay_on else {}
        # An overlay's base already includes its pool's own unprocessed Swap logs.
        if any(l['address'].lower() in self.v3|{POOL,PYTH} and not (overlays and self.swap_pool(l)) for l in self.logs):return None
        pending=[]
        for req,h,stamp in self.pending.values():
            if h not in self.heads or int(self.heads[h]['number'],16)>self.anchor:pending.append(req)
        latest={k:self.header[k] for k in ('timestamp','l1BlockNumber')}
        if self.metadata:
            h=list(self.metadata.values())[-1]
            latest={k:hex(max(int(latest[k],16),int(h[k],16))) for k in latest}
        latest['timestamp']=hex(max(int(latest['timestamp'],16),(now+20_000_000)//10**9))
        oracles=len(pending);speculative=False;uncertain=False
        for pool,overlay in overlays.items():
            sqrt,unknown,_=overlay.view();uncertain=uncertain or unknown
            if sqrt is not None and sqrt!=self.v3_sqrt.get(pool):
                pending.append({'kind':'v3_price','log':overlay.pseudo_log(latest['timestamp'])});speculative=True
        result=self.worker.call(kind='quote',raw_base=str(raw),header=latest,pending=pending)
        self.counts['quotes_v3_speculative']+=speculative
        return dict(result['quote'],state_version=self.version,pending_oracles=oracles,v3_speculative=speculative,v3_uncertain=uncertain,header=latest)
    def swap_pool(self,log):
        address=log['address'].lower()
        return address if address in self.overlays and log['topics'] and log['topics'][0]==SWAP else None
    def overlay_status(self):
        return dict(enabled=self.overlay_on,pools={pool:dict(queued=len(o.txs),uncertain=o.view()[1],counts=dict(o.counts),recent_mismatches=list(o.mismatches)[-5:]) for pool,o in self.overlays.items()}) if self.overlays else None

async def v3_checks(queue,projection,rpc_url,state):
    """Background pinned slot0 read after an overlay surprise. Never on the quote path.
    A difference from the log-derived price turns the overlay off until a later check agrees."""
    from metric_account_observer import HttpRpc
    rpc=HttpRpc(rpc_url)
    while True:
        request=await queue.get()
        try:
            await asyncio.sleep(1)                      # public RPC trails the feed by 0.5-0.9 s; also bounds the rate
            header=None
            for _ in range(20):
                header=await rpc.call('eth_getBlockByNumber',[request['number'],False])
                if header is not None:break
                await asyncio.sleep(.25)
            if header is None or header['hash']!=request['hash']:raise RuntimeError('check block unavailable')
            same=True
            for pool,sqrt in request['sqrt'].items():
                raw=await rpc.call('eth_call',[{'to':pool,'data':'0x3850c7bd'},request['number']])
                same=same and int(raw[2:66],16)==sqrt
            state['checks']=state.get('checks',0)+1;state['differences']=state.get('differences',0)+(not same)
            state['last']=dict(block=request['number'],same=same,checked_ns=time.time_ns())
            projection.overlay_on=same
            if not same:projection.v3_check_wanted=True
        except Exception as exc:
            state['errors']=state.get('errors',0)+1;state['last_error']=str(exc)[:200]

async def stream(kind,url,queue,timeout_seconds=10):
    async with websockets.connect(url,max_size=32*1024*1024,ping_interval=10,ping_timeout=10) as ws:
        if kind=='chain':
            for i,subscription in [(1,'logs'),(2,'newHeads')]:
                await ws.send(json.dumps(dict(jsonrpc='2.0',id=i,method='eth_subscribe',params=[subscription,{}] if i==1 else[subscription])))
        subscriptions={}
        while True:
            message=await asyncio.wait_for(ws.recv(),timeout_seconds)
            stamp=time.time_ns();r=json.loads(message)
            if kind=='chain':
                if 'id' in r:
                    if 'error' in r:raise ValueError(r['error'])
                    subscriptions[r['result']]='log' if r['id']==1 else'head';continue
                p=r.get('params',{});event=subscriptions.get(p.get('subscription'))
                if event:queue.put_nowait((event,p['result'],stamp))
            elif kind=='nitro':
                if 'raw' in r:stamp=r['relay_recv_ns'];r=json.loads(r['raw'])
                queue.put_nowait(('nitro',r,stamp))
            else:queue.put_nowait(('bbo',r,stamp))
    raise ValueError(kind+' websocket closed')

async def run(c):
    worker=Worker();q=asyncio.Queue(maxsize=200000);tasks=[];writer=None
    health={'account_ready':False};epoch=time.time_ns()
    stats={'phase':'connecting','ready':False,'started_ns':time.time_ns()}
    save(c['status'],stats)
    try:
        for kind,url in [('chain',c['chain_ws']),('nitro',c['nitro_ws']),('bbo',c['binance_ws'])]:
            tasks.append(asyncio.create_task(stream(kind,url,q,c['stream_timeout_seconds'])))
        # A stable initial pushed window must precede the pinned checkpoint.
        await asyncio.sleep(2)
        for task in tasks:
            if task.done():task.result()
        stats['phase']='bootstrap';save(c['status'],stats)
        with open(c['bootstrap_log'],'w') as log:
            process=await asyncio.create_subprocess_exec(sys.executable,'scripts/bootstrap_known_slots.py','--template',c['template'],'--config',c['pool_config'],'--output',c['checkpoint'],'--rpc',c['bootstrap_rpc'],'--batch-size','25','--batch-interval','1.2',stdout=log,stderr=log)
            try:
                deadline=time.monotonic()+900
                while process.returncode is None:
                    for task in tasks:
                        if task.done():task.result()
                    if time.monotonic()>deadline:raise TimeoutError('checkpoint bootstrap timeout')
                    try:await asyncio.wait_for(process.wait(),1)
                    except asyncio.TimeoutError:pass
                if process.returncode:raise ValueError('bootstrap failed; see '+c['bootstrap_log'])
            finally:
                if process.returncode is None:process.kill();await process.wait()
        for task in tasks:
            if task.done():task.result()
        seed=json.loads(Path(c['checkpoint']).read_text());projection=Projection(worker);projection.initialize(seed)
        stats['phase']='catchup';save(c['status'],stats)
        from metric_pool_audit import run_audits
        audit_queue=asyncio.Queue(maxsize=1);projection.audit_queue=audit_queue
        projection.audit_interval_ns=c['audit_interval_seconds']*10**9
        projection.next_audit_ns=time.time_ns()+5_000_000_000
        health['last_audit_ns']=time.time_ns()
        tasks.append(asyncio.create_task(run_audits(audit_queue,seed['pools'][0]['provider'],health,c)))
        v3_rpc={}
        if c.get('v3_overlay',{}).get('enabled'):
            o=c['v3_overlay']
            for pool in o['pools']:
                if pool.lower() not in projection.v3:raise ValueError('V3 overlay pool is not a price dependency')
                projection.overlays[pool.lower()]=build_overlay(pool,o['registry'],o['touchers'])
            projection.v3_check_queue=asyncio.Queue(maxsize=1)
            tasks.append(asyncio.create_task(v3_checks(projection.v3_check_queue,projection,o.get('rpc') or c['bootstrap_rpc'],v3_rpc)))
        trader_config=json.loads(Path(c['trader_config']).read_text()) if c.get('trader_config') else None
        if trader_config and trader_config.get('executor'):
            from metric_account_observer import observe
            setup=json.loads(Path(c['setup_journal']).read_text());projection.wallet=setup['steps']['deploy']['signed']['wallet'];projection.executor=setup['executor'].lower()
            reader,writer=await asyncio.open_unix_connection(trader_config['input_socket'])
            writer.write(MAGIC);await writer.drain()
            lock=asyncio.Lock()
            async def send(row):
                raw=encode(row)
                async with lock:
                    writer.write(struct.pack('<I',len(raw))+raw);await writer.drain()
            async def receive_states():
                if await reader.readexactly(8)!=MAGIC:raise ValueError('trader IPC magic')
                while True:
                    n=struct.unpack('<I',await reader.readexactly(4))[0]
                    if not 0<n<=1024*1024:raise ValueError('trader IPC length')
                    state=decode(await reader.readexactly(n))
                    if state.get('kind')!='trader_state':continue
                    health['trader']=state
                    health['account_ready']=state.get('account_epoch')==epoch and not state.get('pending_hash')
            tasks.append(asyncio.create_task(receive_states()))
            tasks.append(asyncio.create_task(observe(c['trader_config'],c['setup_journal'],send,health,epoch)))
        else:send=None
        bbo=None;last_status=0;last_quote=0;quotes=0;last_error=None;last_price=None
        while True:
            for task in tasks:
                if task.done():task.result()
            try:kind,value,stamp=await asyncio.wait_for(q.get(),.025)
            except asyncio.TimeoutError:kind=None
            if kind=='bbo':bbo=(value,stamp)
            elif kind:projection.update(kind,value,stamp)
            now=time.time_ns()
            if q.empty():
                projection.check_progress(now,c['stream_timeout_seconds']*10**9)
                if now-health['last_audit_ns']>c['audit_max_age_seconds']*10**9:raise RuntimeError('pool audit expired')
            while send and projection.timings:await send(projection.timings.popleft())
            trader_state=health.get('trader',{})
            while send and projection.effects and (trader_state.get('head') or 0)>=int(projection.effects[0]['receipt']['blockNumber'],16):
                effect=projection.effects.popleft()
                if effect['receipt']['transactionHash']==trader_state.get('pending_hash'):await send(effect)
            if q.empty() and (now-last_quote>=25_000_000 or kind in ('nitro','log')) and bbo and now-bbo[1]<1_000_000_000:
                raw=int(Decimal('99.8')/Decimal(bbo[0]['a'])*10**18)
                trader_status=health.get('trader',{})
                inventory=trader_status.get('inventory')
                if inventory and int(inventory['base'])>int(trader_status['baseline_raw']):
                    raw=int(inventory['base'])-int(trader_status['baseline_raw'])
                try:
                    price=projection.quote(raw,now)
                    if price:
                        last_price=dict(price,raw_base=str(raw),received_ns=now)
                        quotes+=1;last_error=None
                        if send and health['account_ready'] and price.get('bid_raw') and price.get('ask_raw'):
                            await send(dict(kind='quote',observation=dict(pool=list(bytes.fromhex(POOL[2:])),epoch=epoch,state_version=projection.version,state_valid=True,state_received_ns=now,bbo_received_ns=bbo[1],provider_valid_until_ns=now+50_000_000,bid_e8=str(int(Decimal(bbo[0]['b'])*10**8)),ask_e8=str(int(Decimal(bbo[0]['a'])*10**8)),quantity=str(raw),pool_bid_usdg=price['bid_raw'],pool_ask_usdg=price['ask_raw'])))
                except ValueError as exc:
                    # Quote rejection (e.g. provider timeout) leaves confirmed
                    # storage intact; it does not make an executable quote.
                    last_error=str(exc);last_price=None
                last_quote=now
            if now-last_status>=1_000_000_000:
                stats.update(phase='connected' if send else 'shadow',ready=bool(health['account_ready'] and last_price),account=health,updated_ns=now,counts=dict(projection.counts),quotes=quotes,last_quote=last_price,last_quote_error=last_error,buffered=q.qsize(),pending_logs=len(projection.logs),anchor_seen=projection.anchor_seen,hot_path_rpc_requests=0,audit_local_error=projection.audit_local_error,v3_overlay=projection.overlay_status(),v3_rpc_checks=v3_rpc)
                save(c['status'],stats);last_status=now
    except Exception as exc:
        stats.update(phase='invalid',ready=False,error=str(exc),updated_ns=time.time_ns());save(c['status'],stats)
        raise
    finally:
        for task in tasks:task.cancel()
        await asyncio.gather(*tasks,return_exceptions=True)
        if writer:writer.close()
        worker.close()

async def supervise(c):
    delay=c['recovery_initial_seconds']
    while True:
        started=time.monotonic()
        try:await run(c)
        except asyncio.CancelledError:raise
        except Exception as exc:
            print('observer recovering:',str(exc),flush=True)
        if time.monotonic()-started>300:delay=c['recovery_initial_seconds']
        await asyncio.sleep(delay)
        delay=min(c['recovery_max_seconds'],delay*2)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('config');a=p.parse_args()
    asyncio.run(supervise(json.loads(Path(a.config).read_text())))
