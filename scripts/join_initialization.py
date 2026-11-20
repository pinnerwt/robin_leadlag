"""Join independently read quote/dependency snapshots only at the identical anchor."""
import argparse,copy,json
from pathlib import Path
def join(quote,dependencies):
 if not quote.get('quote_state_complete'):raise ValueError('quote state incomplete')
 if quote['anchor']['hash']!=dependencies['anchor']['hash'] or quote['anchor']['number']!=dependencies['anchor']['number']:raise ValueError('different initialization anchors')
 accounts=copy.deepcopy(dependencies['accounts'])
 for account in accounts.values():account['storage']={hex(int(k,16)):hex(int(v,16)) for k,v in account.get('storage',{}).items()}
 for address,account in quote['accounts'].items():
  dst=accounts.setdefault(address.lower(),{})
  for field in ('balance','nonce','code'):
   if field not in account:continue
   if field in dst:
    left,right=dst[field],account[field]
    if field=='code':same=left.lower()==right.lower()
    else:same=(int(left,16) if isinstance(left,str) else left)==(int(right,16) if isinstance(right,str) else right)
    if not same:raise ValueError(f'account disagreement {address} {field}')
   else:dst[field]=account[field]
  slots=dst.setdefault('storage',{})
  for key,value in account.get('storage',{}).items():
   key=hex(int(key,16));value=hex(int(value,16))
   if key in slots and slots[key]!=value:raise ValueError(f'storage disagreement {address} {key}')
   slots[key]=value
 result=copy.deepcopy(quote);result.update(accounts=accounts,hydration=dependencies['hydration'],execution_state_complete=False,
  evm_dependency_coverage='pre_anchor_discovery_and_explicit_initialization_queries',rpc_phase='initialization_only')
 return result
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('quotes',type=Path);p.add_argument('dependencies',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
 result=join(json.loads(a.quotes.read_text()),json.loads(a.dependencies.read_text()));a.output.write_text(json.dumps(result,separators=(',',':'))+'\n');print('joined',len(result['accounts']),'accounts',sum(len(x.get('storage',{})) for x in result['accounts'].values()),'slots')
