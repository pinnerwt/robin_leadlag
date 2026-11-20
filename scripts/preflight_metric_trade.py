"""One-time execution-path simulation; eth_call only, never sends a trade."""
import asyncio,json,sys,time
from pathlib import Path
from metric_account_observer import HttpRpc,word
from metric_live_observer import POOL,save
async def main():
 c=json.loads(Path(sys.argv[1]).read_text());s=json.loads(Path(sys.argv[2]).read_text())
 rpc=HttpRpc('https://rpc.mainnet.chain.robinhood.com')
 head=await rpc.call('eth_getBlockByNumber',['latest',False]);deadline=int(head['timestamp'],16)+60
 wallet=s['steps']['deploy']['signed']['wallet'];rows=[]
 for buy in [True,False]:
  data='0x5ea575e1'+word(POOL)+word(int(buy))+word(10**15)+word(100_000_000 if buy else 1)+word(deadline)
  response=await rpc.call('eth_call',[{'from':wallet,'to':c['executor'],'data':data,'gas':hex(c['gas_limit'])},head['number']])
  rows.append(dict(side='buy' if buy else 'sell',base_raw=str(10**15),usdg_raw=str(int(response,16))))
 if (await rpc.call('eth_getBlockByNumber',[head['number'],False]))['hash']!=head['hash']:raise ValueError('preflight reorg')
 result=dict(wallet=wallet,executor=c['executor'],block=head['number'],hash=head['hash'],checks=rows,submitted=False,checked_ns=time.time_ns())
 save('reports/metric-trade-preflight.json',result);print(json.dumps(result))
asyncio.run(main())
