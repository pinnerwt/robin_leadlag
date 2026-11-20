"""Same-checkpoint beforeSwap counterfactuals; missing state remains an error."""
import argparse,copy,json,subprocess,tempfile
from pathlib import Path

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--sender-disabled',action='store_true');args=ap.parse_args()
 source_path='reports/amm/delegated-wrapper-hook-'+('sender-disabled-initialized' if args.sender_disabled else 'initialized-probe')+'.json'
 source=json.loads(Path(source_path).read_text());assert source['anchor_verified'];raw=bytes.fromhex(source['tx']['data'][2:]);cases=[];requests=[]
 for zero in (False,True):
  for amount in (10**6,10**18,10**22):
   tx=copy.deepcopy(source['tx']);data=bytearray(raw)
   # beforeSwap words: sender, five key fields, direction, amount, limit, bytes.
   data[4+6*32:4+7*32]=int(zero).to_bytes(32,'big')
   data[4+7*32:4+8*32]=((-amount)%(1<<256)).to_bytes(32,'big')
   tx.update(tx=f'hook-{zero}-{amount}',data='0x'+data.hex());requests.append(tx);cases.append(dict(zero=zero,amount=amount))
 with tempfile.NamedTemporaryFile(suffix='.json') as tmp:
  Path(tmp.name).write_text(json.dumps(source['seed']))
  results=list(map(json.loads,subprocess.check_output(['target/release/examples/router_prefix',tmp.name],input=''.join(json.dumps(tx)+'\n' for tx in requests),text=True).splitlines()))
 for case,result in zip(cases,results):
  case['result']=result;print(case['zero'],case['amount'],result['error'],result.get('output'),flush=True)
 Path('reports/amm/delegated-wrapper-hook-'+('sender-disabled-' if args.sender_disabled else '')+'variants.json').write_text(json.dumps(dict(synthetic_sender_disabled=args.sender_disabled,source=source_path,anchor=source['seed']['anchor']['hash'],cases=cases,caveat='Counterfactual direction/amount only, same sender and pool key. Original limit retained; no manager/curve execution.'),indent=2)+'\n')
if __name__=='__main__':main()
