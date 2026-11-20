"""Research-only historical prestate/diff witness collection for offline replay.
Per-transaction prestates are diagnostic fixtures, never a continuous checkpoint.
"""
import json,argparse
from pathlib import Path
from bootstrap_state import Bootstrap
p=argparse.ArgumentParser(description=__doc__);p.add_argument('txs');p.add_argument('--output',default='captures/signed-router-fixtures.json');a=p.parse_args();b=Bootstrap('https://rpc-robinhood.blockmachine.io');out=[]
for tx in map(json.loads,open(a.txs)):
 pre=b.rpc('debug_traceTransaction',[tx['tx'],{'tracer':'prestateTracer'}])
 diff=b.rpc('debug_traceTransaction',[tx['tx'],{'tracer':'prestateTracer','tracerConfig':{'diffMode':True}}])
 trace=b.rpc('debug_traceTransaction',[tx['tx'],{'tracer':'callTracer','tracerConfig':{'withLog':True}}])
 receipt=b.rpc('eth_getTransactionReceipt',[tx['tx']])
 out.append(dict(tx=tx,accounts=pre,diff=diff,trace=trace,receipt=receipt))
 Path(a.output).write_text(json.dumps(out,indent=2)+'\n');print(tx['tx'],'accounts',len(pre),'gas',receipt['gasUsed'],flush=True)
