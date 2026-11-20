"""Research only: collect historical block context and fee-account witnesses."""
import json,argparse
from pathlib import Path
from bootstrap_state import Bootstrap
from arbos_units import ARBOS,ROOT
ap=argparse.ArgumentParser();ap.add_argument('--fixtures',default='captures/signed-router-fixtures.json');args=ap.parse_args();p=Path(args.fixtures);rows=json.loads(p.read_text());b=Bootstrap('https://rpc-robinhood.blockmachine.io');headers={}
for r in rows:
 h=r['tx']['block_hash']
 if 'header' not in r:raise ValueError('recorded header required; no historical block RPC')
 s={hex(int(k,16)):int(v,16) for k,v in r['accounts'][ARBOS]['storage'].items()};addresses=['0x'+s[ROOT+x].to_bytes(32,'big')[-20:].hex() for x in ('03','06')]
 tracer='''{seen:false,addresses:ADDRESSES,before:{},read:function(db){var o={};for(var i=0;i<this.addresses.length;i++){var a=this.addresses[i];o[a]={balance:db.getBalance(toAddress(a)).toString(16),nonce:db.getNonce(toAddress(a)),code:toHex(db.getCode(toAddress(a)))};}return o;},step:function(log,db){if(!this.seen){this.seen=true;this.before=this.read(db);}},fault:function(log,db){},result:function(ctx,db){return {before:this.before,after:this.read(db)};}}'''.replace('ADDRESSES',json.dumps(addresses))
 try:r['fee_account_witness']=b.rpc('debug_traceTransaction',[r['tx']['tx'],{'tracer':tracer}])
 except Exception as e:r['fee_witness_error']=str(e)
 p.write_text(json.dumps(rows,indent=2)+'\n');print(r['tx']['tx'],'basefee',r['header']['baseFeePerGas'],'fee_witness',bool(r.get('fee_account_witness')),'error',r.get('fee_witness_error'),flush=True)
