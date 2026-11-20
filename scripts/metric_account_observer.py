"""Independent cold/background account and receipt observer; never called by quotes."""
import asyncio,json,time,urllib.request,contextlib
from pathlib import Path
import websockets
from setup_metric_executor import Rpc
from metric_live_observer import POOL
BASE='0x0bd7d308f8e1639fab988df18a8011f41eacad73'
QUOTE='0x5fc5360d0400a0fd4f2af552add042d716f1d168'
def word(x):return format(int(x,16) if isinstance(x,str) else x,'064x')
def words(x):return [int(x[i:i+64],16) for i in range(2,len(x),64)]

class RpcError(ValueError):
    def __init__(self,method,error):self.error=error;super().__init__(f"{method}: {error}")

class HttpRpc:
    def __init__(self,url):self.url=url;self.sequence=0
    async def call(self,method,params):
        self.sequence+=1;ident=self.sequence
        def request():
            req=urllib.request.Request(self.url,data=json.dumps(dict(jsonrpc='2.0',id=ident,method=method,params=params)).encode(),headers={'Content-Type':'application/json','User-Agent':'robin-leadlag/0.1'})
            with urllib.request.urlopen(req,timeout=15) as response:r=json.load(response)
            if r.get("id")!=ident:raise ValueError("RPC response identity mismatch")
            if "error" in r:raise RpcError(method,r["error"])
            return r['result']
        return await asyncio.to_thread(request)

async def observe(config_path, setup_path, send, health, epoch):
    while True:
        try:await observe_session(config_path,setup_path,send,health,epoch)
        except Exception as exc:
            health.update(account_ready=False,last_account_error=str(exc))
            await send(dict(kind='gap',reason='account observer unavailable'))
            await asyncio.sleep(5)

async def observe_session(config_path, setup_path, send, health, epoch):
    c=json.loads(Path(config_path).read_text());setup=json.loads(Path(setup_path).read_text())
    executor=setup['executor'];wallet=setup['steps']['deploy']['signed']['wallet']
    if c['executor']!=executor or c['executor_codehash']!=setup['executor_codehash']:raise ValueError('executor configuration mismatch')
    expected_runtime=setup['steps']['deploy']['signed']['expected_runtime']
    poolhash=setup['steps']['configure']['plan']['pool_codehash']
    async with contextlib.AsyncExitStack():
        rpc=HttpRpc('https://rpc.mainnet.chain.robinhood.com')
        if int(await rpc.call('eth_chainId',[]),16)!=4663:raise ValueError('wrong account chain')
        last_sync=0;last_receipt=None;last_receipt_ns=0
        while True:
            now=time.time_ns();status=health.get('trader',{})
            if not status or now-status.get('updated_ns',0)>2_000_000_000:
                await asyncio.sleep(.05);continue
            pending=status.get('pending_hash')
            if pending:
                receipt=await rpc.call('eth_getTransactionReceipt',[pending])
                if receipt and (pending!=last_receipt or now-last_receipt_ns>2_000_000_000) and status.get('head',0)>=int(receipt['blockNumber'],16):
                    receipt=dict(receipt,_source='rpc',_observed_ns=time.time_ns())
                    await send(dict(kind='receipt',receipt=receipt));last_receipt=pending;last_receipt_ns=now;last_sync=0
                await asyncio.sleep(.1);continue
            if now-last_sync<2_000_000_000:
                await asyncio.sleep(.1);continue
            head=await rpc.call('eth_getBlockByNumber',['latest',False]);block=head['number']
            async def call(to,data):return await rpc.call('eth_call',[{'from':wallet,'to':to,'data':data},block])
            if (await rpc.call('eth_getCode',[executor,block])).lower()!=expected_runtime.lower():raise ValueError('executor runtime changed')
            if int(await call(executor,'0x8da5cb5b'),16)!=int(wallet,16):raise ValueError('executor owner mismatch')
            binding=words(await call(executor,'0xa4063dbc'+word(POOL)))
            if binding!=[int(BASE,16),int(QUOTE,16),1,int(poolhash,16)]:raise ValueError('pool binding mismatch')
            # Background access proof only; never used as the quote or signal.
            try:
                prices=words(await call(POOL,'0xec069057'))
                access=len(prices)==2 and 0<prices[0]<=prices[1]
            except ValueError:access=False
            if not access:
                health['last_account_error']='provider access unavailable'
                await asyncio.sleep(1);continue
            base=int(await call(BASE,'0x70a08231'+word(wallet)),16)
            cash=int(await call(QUOTE,'0x70a08231'+word(wallet)),16)
            ba=int(await call(BASE,'0xdd62ed3e'+word(wallet)+word(executor)),16)
            qa=int(await call(QUOTE,'0xdd62ed3e'+word(wallet)+word(executor)),16)
            native=int(await rpc.call('eth_getBalance',[wallet,block]),16)
            nonce=int(await rpc.call('eth_getTransactionCount',[wallet,block]),16)
            pending_nonce=int(await rpc.call('eth_getTransactionCount',[wallet,'pending']),16)
            if nonce!=pending_nonce:
                health['last_account_error']='pending nonce during snapshot';await asyncio.sleep(.2);continue
            if (await rpc.call('eth_getBlockByNumber',[block,False]))['hash']!=head['hash']:raise ValueError('account snapshot reorg')
            # Wait for the independent trader head subscriber to observe this anchor.
            for _ in range(100):
                status=health.get('trader',{})
                if (status.get('head') or 0)>=int(block,16):break
                await asyncio.sleep(.01)
            else:raise ValueError('account anchor not observed by trader')
            if status.get('pending_hash'):continue
            if status.get('inventory') and (int(status['inventory']['base'])!=base or int(status['inventory']['cash'])!=cash):
                # A pushed receipt may have settled while this snapshot was in flight.
                if int(status.get('last_settled_block') or 0)>int(block,16):continue
                raise ValueError('unexpected external wallet balance change')
            account=dict(nonce=nonce,cash=str(cash),positions={'ETH':str(base)},native=str(native),observed_ns=time.time_ns(),permissions={'ETH':dict(executor_verified=True,provider_access_verified=True,base_allowance=str(ba),quote_allowance=str(qa))})
            await send(dict(kind='synchronize',epoch=epoch,anchor_number=int(block,16),anchor_hash=head['hash'],executor_codehash=setup['executor_codehash'],account=account))
            health.update(last_account_error=None,last_account_sync_ns=time.time_ns(),base_raw=str(base),cash_raw=str(cash))
            last_sync=time.time_ns()
