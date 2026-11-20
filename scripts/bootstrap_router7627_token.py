"""Startup-only same-anchor WETH dependency capture; never a hot-path fetch."""
import argparse,json
from pathlib import Path
from bootstrap_state import Bootstrap,mapping
from router7627_second_leg import ROUTER
TOKEN='0x0bd7d308f8e1639fab988df18a8011f41eacad73'
IMPLEMENTATION='0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc'
ADMIN='0xb53127684a568b3173ae13b9f8a6016e243e63b6e8ee1178d6a717850b5d6103'

def capture(rpc,head):
 block=head['number']
 def verify():
  actual=rpc('eth_getBlockByNumber',[block,False])
  if not actual or actual['hash']!=head['hash']:raise ValueError('anchor mismatch')
 verify()
 slots=[IMPLEMENTATION,ADMIN,'0x35',mapping(int(ROUTER,16),0x33)]
 storage={slot:rpc('eth_getStorageAt',[TOKEN,slot,block]) for slot in slots}
 implementation=int(storage[IMPLEMENTATION],16)
 if not 0<implementation<1<<160:raise ValueError('invalid proxy implementation')
 impl='0x'+implementation.to_bytes(20,'big').hex()
 accounts={}
 for address in (TOKEN,impl):
  code=rpc('eth_getCode',[address,block])
  if code=='0x':raise ValueError('missing token or implementation code')
  accounts[address]=dict(code=code,balance=rpc('eth_getBalance',[address,block]),nonce=int(rpc('eth_getTransactionCount',[address,block]),16),storage=storage if address==TOKEN else {})
 verify()
 return dict(anchor=head,accounts=accounts,kind='router7627_weth_dependencies',rpc_phase='initialization_only',complete=False,execution_state_complete=False,router=ROUTER,implementation=impl,caveat='Known token dependencies only. Must join exclusively with identical-anchor checkpoint; pool and observation state not included. Changed code requires decoder revalidation.')

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--anchor',required=True,help='JSON checkpoint containing anchor header');p.add_argument('--output',required=True);p.add_argument('--rpc',default='https://rpc-robinhood.blockmachine.io');a=p.parse_args()
 output=Path(a.output)
 if output.exists():raise ValueError('refuse to overwrite checkpoint')
 head=json.loads(Path(a.anchor).read_text())['anchor'];b=Bootstrap(a.rpc)
 result=capture(b.rpc,head);result['rpc_calls']=b.calls
 with output.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
 print(json.dumps(dict(anchor=head['number'],rpc_calls=b.calls,output=str(output))))
if __name__=='__main__':main()
