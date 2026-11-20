"""Cold, resumable B89 executor setup. Key is read only by the local Rust signer.
No swaps. Persist signed bytes before submission; never replace an uncertain nonce.
"""
import argparse,asyncio,json,subprocess,time,os
from pathlib import Path
import websockets
from metric_live_observer import save,POOL

class Rpc:
    def __init__(self, ws):self.ws=ws;self.sequence=0
    async def call(self,method,params):
        self.sequence+=1
        await self.ws.send(json.dumps(dict(jsonrpc='2.0',id=self.sequence,method=method,params=params)))
        response=json.loads(await asyncio.wait_for(self.ws.recv(),30))
        if response.get('id')!=self.sequence or 'error' in response:raise ValueError(f'{method}: {response.get("error", "invalid response")}')
        return response['result']

def sign(config, request):
    p=subprocess.run(['target/release/metric-setup-sign',config],input=json.dumps(request),text=True,capture_output=True)
    if p.returncode:raise ValueError('setup signer rejected request: '+p.stderr.strip())
    return json.loads(p.stdout)

async def run(args):
    c=json.loads(Path(args.config).read_text())
    if c['mode']!='standby':raise ValueError('trader must be standby during setup')
    journal=Path(args.journal)
    state=json.loads(journal.read_text()) if journal.exists() else {'steps':{}}
    async with websockets.connect(c['chain_ws_url']) as ws:
        rpc=Rpc(ws)
        if int(await rpc.call('eth_chainId',[]),16)!=4663:raise ValueError('wrong chain')
        for action in ['deploy','configure','approve_base','approve_quote']:
            entry=state['steps'].get(action)
            if entry and entry.get('receipt'):
                receipt=entry['receipt'];head=await rpc.call('eth_getBlockByNumber',[receipt['blockNumber'],False])
                if head['hash']!=receipt['blockHash']:raise ValueError('setup receipt reorg')
                if int(receipt['status'],16)!=1:raise ValueError('prior setup reverted')
                continue
            if not entry:
                info=json.loads(subprocess.check_output(['target/release/metric-trader',args.config,'--check-credentials'],text=True))
                wallet=info['wallet'];nonce=int(await rpc.call('eth_getTransactionCount',[wallet,'latest']),16)
                if nonce!=int(await rpc.call('eth_getTransactionCount',[wallet,'pending']),16):raise ValueError('pending external transaction')
                code=await rpc.call('eth_getCode',[POOL,'latest'])
                poolhash=sign(args.config,dict(action='hash',data=code))['hash']
                request=dict(action=action,nonce=nonce,gas=2_000_000,max_fee='1000000000',executor=state.get('executor'),pool_codehash=poolhash)
                signed=sign(args.config,request)
                call={'from':wallet,'data':signed['data'],'value':'0x0'}
                if signed['to']:call['to']=signed['to']
                estimate=int(await rpc.call('eth_estimateGas',[call]),16)
                request['gas']=min(2_000_000,estimate*12//10+10000)
                if estimate>request['gas']:raise ValueError('setup gas exceeds cap')
                signed=sign(args.config,request)
                entry=dict(plan=request,signed=signed,created_ns=time.time_ns());state['steps'][action]=entry
                save(journal,state)
                with journal.open('rb') as f:os.fsync(f.fileno())
            signed=entry['signed']
            receipt=await rpc.call('eth_getTransactionReceipt',[signed['hash']])
            if receipt is None:
                if not args.execute:
                    print(json.dumps(dict(action=action,phase='prepared',gas=entry['plan']['gas'])));return
                # Re-broadcast identical bytes only, including on process recovery.
                returned=await rpc.call('eth_sendRawTransaction',[signed['raw']])
                if returned.lower()!=signed['hash'].lower():raise ValueError('submission hash mismatch')
                for _ in range(120):
                    await asyncio.sleep(.5)
                    receipt=await rpc.call('eth_getTransactionReceipt',[signed['hash']])
                    if receipt:break
                else:raise ValueError('receipt pending; durable bytes retained')
            if int(receipt['status'],16)!=1:raise ValueError(action+' reverted: '+signed['hash'])
            head=await rpc.call('eth_getBlockByNumber',[receipt['blockNumber'],False])
            if head['hash']!=receipt['blockHash']:raise ValueError('noncanonical setup receipt')
            if action=='deploy':
                executor=receipt['contractAddress']
                code=await rpc.call('eth_getCode',[executor,receipt['blockNumber']])
                if code.lower()!=signed['expected_runtime'].lower():raise ValueError('deployed runtime differs from compiled owner-bound artifact')
                state['executor']=executor;state['executor_codehash']=sign(args.config,dict(action='hash',data=code))['hash']
            entry['receipt']=receipt;save(journal,state)
            print(json.dumps(dict(action=action,tx=signed['hash'],block=receipt['blockNumber'],executor=state.get('executor'))),flush=True)
        c['executor']=state['executor'];c['executor_codehash']=state['executor_codehash'];save(args.config,c)
        print('Executor configured with finite approvals. Trader mode remains standby.')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',required=True);p.add_argument('--journal',required=True);p.add_argument('--execute',action='store_true');a=p.parse_args()
    asyncio.run(run(a))
