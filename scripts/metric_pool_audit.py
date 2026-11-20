"""Independent, pinned-block quote parity audit. Never runs on the signal path."""
import asyncio,time,json
from metric_live_observer import POOL,save
from metric_account_observer import HttpRpc,RpcError

def word(n):return format(n%(1<<256),'064x')
def words(raw):return [int(raw[i:i+64],16) for i in range(2,len(raw),64)]
def compare(local,remote,tolerance):
    if local is None or remote is None:
        if local!=remote:raise ValueError('quote availability mismatch')
        return 0.
    if int(local)<=0 or int(remote)<=0:raise ValueError('nonpositive quote')
    error=abs(int(local)-int(remote))/int(remote)*10000
    if error>tolerance:raise ValueError(f'quote divergence {error:.6f} bps exceeds {tolerance}')
    return error

async def run_audits(queue,provider,health,config):
    rpc=HttpRpc(config['bootstrap_rpc'])
    while True:
        request=await queue.get();block=request['number'];result=dict(block=block,hash=request['hash'],started_ns=time.time_ns())
        try:
            header=None
            # Push feeds can lead the public RPC index. Wait only in this audit task.
            for _ in range(40):
                header=await rpc.call('eth_getBlockByNumber',[block,False])
                if header is not None:break
                await asyncio.sleep(.25)
            if header is None:raise RuntimeError('audit block not yet available from RPC')
            if header['hash']!=request['hash']:raise ValueError('audit anchor reorg')
            remote=await rpc.call('eth_call',[{'to':provider,'data':'0x171755b1'},block])
            prices=words(remote)
            if len(prices)!=3:raise ValueError('provider price length')
            errors=[compare(a,b,config['audit_tolerance_bps']) for a,b in zip(words(request['local']['prices']),prices)]
            checks=[]
            for row in request['local']['quotes']:
                quantity=int(row['raw_base'])
                for sell in (True,False):
                    side='bid' if sell else 'ask'
                    args=[0,0,int(sell),quantity if sell else -quantity,1 if sell else (1<<128)-1,*prices,288,0]
                    data='0x658b6cb7'+''.join(word(x) for x in args)
                    try:
                        raw=await rpc.call('eth_call',[{'to':POOL,'data':data},block])
                    except RpcError as exc:
                        raw=exc.error.get('data','')
                        if not isinstance(raw,str):raw=''
                    value=None
                    if raw.startswith('0x1f6053de') and len(raw)==138:
                        ds=[int(raw[i:i+64],16) for i in (10,74)];ds=[x-(1<<256)if x>>255 else x for x in ds]
                        if ds[0]==(quantity if sell else -quantity):value=str(abs(ds[1]))
                    error=compare(row['quote'].get(side+'_raw'),value,config['audit_tolerance_bps']);errors.append(error)
                    checks.append(dict(raw_base=str(quantity),side=side,local=row['quote'].get(side+'_raw'),remote=value,error_bps=error))
            if (await rpc.call('eth_getBlockByNumber',[block,False]))['hash']!=request['hash']:raise ValueError('audit anchor changed')
            result.update(passed=True,checks=checks,max_error_bps=max(errors),finished_ns=time.time_ns())
            health.update(last_audit_ns=time.time_ns(),audit_error=None,audit_max_error_bps=max(errors))
        except RpcError as exc:
            result.update(passed=False,inconclusive=True,error=str(exc));health["audit_error"]=str(exc)
        except ValueError as exc:
            result.update(passed=False,error=str(exc));save(config['audit_report'],result)
            raise RuntimeError('pool audit failed: '+str(exc))
        except Exception as exc:
            # Transport trouble never refreshes the last successful audit clock.
            result.update(passed=False,inconclusive=True,error=str(exc));health['audit_error']=str(exc)
        save(config['audit_report'],result)
