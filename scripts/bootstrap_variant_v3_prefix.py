"""Bounded new-anchor V3 swap storage discovery with explicit settlement mocks."""
import argparse,json,re
from pathlib import Path
from bootstrap_state import Bootstrap
from probe_delegated_kind8 import run
P='0xf55045c021949b202a5d10451b2ffa01561c5f55'
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--downstream',action='store_true');args=ap.parse_args()
 s=json.loads(Path('reports/amm/variant-code-checkpoint.json').read_text());s['trace_execution']=True;s['getters']={}
 source=json.loads(Path('reports/amm/batch-variant-continuation.json').read_text())['cases'][1];call=source['result']['calls'][0];h=s['anchor']
 b=Bootstrap('https://rpc-robinhood.blockmachine.io')
 if args.downstream:
  upstream=json.loads(Path('reports/amm/variant-v3-curve-parity.json').read_text())
  if upstream['anchor']!=h['hash'] or not all(upstream['checks'].values()):raise ValueError('upstream anchor/parity')
  call=dict(json.loads(Path('reports/amm/settler-variant-actions.json').read_text())['cases'][2]['result']['calls'][0])
  amount=-upstream['fill']['amount0']-1;raw=bytes.fromhex(call['data'][2:]);call['data']='0x'+(raw[:68]+amount.to_bytes(32,'big')+raw[100:]).hex()
  address=call['to'];s['accounts'][address]=dict(code=b.rpc('eth_getCode',[address,h['number']]),balance=b.rpc('eth_getBalance',[address,h['number']]),nonce=b.rpc('eth_getTransactionCount',[address,h['number']]),storage={})
 tx=dict(source['tx'],to=call['to'],data=call['data'],timestamp=int(h['timestamp'],16),sequence=int(h['number'],16),**{'from':call['caller'].lower()})
 for a in [tx['from'],'0x'+'00'*20]:s['accounts'][a]=dict(code='0x00' if a==tx['from'] and args.downstream else '0x',balance='0x0',nonce='0x0',storage={})
 reads=[];stages=[];synthetic=[dict(kind='callback_code_placeholder',address=tx['from'])] if args.downstream else []
 for _ in range(40):
  r=run(s,tx);stages.append(r);error=r.get('error') or ''
  missing=re.search(r'unknown slot (0x[0-9a-fA-F]{40}) (0x[0-9a-fA-F]+)',error)
  if missing:
   address,slot=missing[1].lower(),missing[2];value=b.rpc('eth_getStorageAt',[address,slot,h['number']]);s['accounts'][address]['storage'][slot]=value;reads.append(dict(address=address,slot=slot,value=value));continue
  missing=re.search(r'unknown account (0x[0-9a-fA-F]{40})',error)
  if missing:
   a=missing[1].lower();s['accounts'][a]=dict(code='0x',balance='0x0',nonce='0x0',storage={});synthetic.append(dict(kind='account',address=a));continue
  if len(r['calls'])!=1:break
  c=r['calls'][0];sel=c['data'][:10]
  if sel=='0xa9059cbb':value='0x'+(1).to_bytes(32,'big').hex()
  elif sel=='0x70a08231':value=['0x'+bytes(32).hex(),'0x'+bytes.fromhex(call['data'][10:])[64:96].hex()]
  elif sel=='0xfa461e33' and c['to'].lower()==tx['from']:value='0x'
  else:break
  if c['data'] in s['getters'].get(c['to'],{}):break
  s['getters'].setdefault(c['to'],{})[c['data']]=value;synthetic.append(dict(kind='getter',call=c,value=value))
 verified=b.rpc('eth_getBlockByNumber',[h['number'],False])['hash']==h['hash']
 Path('reports/amm/variant-v3-downstream.json' if args.downstream else 'reports/amm/variant-v3-prefix.json').write_text(json.dumps(dict(seed=s,tx=tx,reads=reads,stages=stages,result=r,synthetic=synthetic,anchor_verified=verified,caveat='New checkpoint original swap size. Explicit token payment/callback mocks; not historical replay.'),indent=2)+'\n')
 print(json.dumps(dict(reads=len(reads),verified=verified,error=r.get('error'),success=r['execution_success'],output=r.get('output'),calls=r['calls'])))
if __name__=='__main__':main()
