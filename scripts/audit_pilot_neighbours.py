"""Historical block/log ordering around pilot orders. Does not submit transactions."""
import asyncio,json,sys,time
from pathlib import Path
from metric_account_observer import HttpRpc
from metric_live_observer import POOL,PYTH,save
V3=['0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca','0x69bfaf19c9f377bb306a89aed9f6b07e2c1a8d9a']
async def main():
 pilot=json.loads(Path('reports/metric-pilot-result.json').read_text());rpc=HttpRpc('https://rpc.mainnet.chain.robinhood.com')
 blocks={};logs={};txs={};windows=[]
 for order,receipt in zip(pilot['orders'],pilot['receipts']):
  n=int(receipt['blockNumber'],16);lo=n-10;hi=n+10
  rows=await rpc.call('eth_getLogs',[dict(fromBlock=hex(lo),toBlock=hex(hi),address=[POOL,PYTH,*V3])])
  for l in rows:logs[(l['blockHash'],l['logIndex'])]=l
  for number in range(n-2,n+3):
   if str(number) not in blocks:blocks[str(number)]=await rpc.call('eth_getBlockByNumber',[hex(number),True])
  for l in rows:
   if l['transactionHash'] not in txs:txs[l['transactionHash']]=await rpc.call('eth_getTransactionByHash',[l['transactionHash']])
  windows.append(dict(order=order,receipt=receipt,from_block=lo,to_block=hi));print('collected',order['tx'],len(rows),flush=True)
 save('reports/pilot-neighbours-raw.json',dict(windows=windows,blocks=blocks,logs=list(logs.values()),transactions=txs,collected_ns=time.time_ns()))
asyncio.run(main())
