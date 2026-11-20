"""Startup-only bounded code discovery; never merged into historical checkpoints."""
import argparse,json
from pathlib import Path
from bootstrap_state import Bootstrap
from initialize_batch_bridge import ROUTER_PINS
ADDRESSES=['0xe3f09600259aebafc83e95901c67821587e8857e','0xf55045c021949b202a5d10451b2ffa01561c5f55']
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,required=True);args=ap.parse_args()
 if args.output.exists():raise ValueError('refusing to overwrite checkpoint')
 entries=json.loads(Path('reports/amm/batch-unpinned-plans.json').read_text())['transactions']
 addresses=list(dict.fromkeys(ADDRESSES+[e['tx']['to'].lower() for e in entries]+list(ROUTER_PINS)+['0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca','0x69bfaf19c9f377bb306a89aed9f6b07e2c1a8d9a']))
 b=Bootstrap('https://rpc-robinhood.blockmachine.io');anchor=b.rpc('eth_getBlockByNumber',['latest',False]);accounts={}
 for address in addresses:
  accounts[address]=dict(code=b.rpc('eth_getCode',[address,anchor['number']]),balance=b.rpc('eth_getBalance',[address,anchor['number']]),nonce=b.rpc('eth_getTransactionCount',[address,anchor['number']]),storage={})
 verified=b.rpc('eth_getBlockByNumber',[anchor['number'],False])['hash']==anchor['hash']
 report=dict(anchor=anchor,accounts=accounts,anchor_verified=verified,rpc_calls=b.calls,caveat='New code-only checkpoint. No storage, no historical replay compatibility.')
 args.output.write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(dict(block=anchor['number'],verified=verified,code_sizes={a:(len(v['code'])-2)//2 for a,v in accounts.items()})))
if __name__=='__main__':main()
