"""Research only: capture fresh pushed reports and immediately obtain witnesses.
Never imported by runtime follower. No swaps or other transactions are sent.
"""
import argparse,asyncio,json,subprocess,time
from pathlib import Path
import websockets
from bootstrap_state import Bootstrap

async def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--seconds',type=int,default=180);p.add_argument('--count',type=int,default=3);p.add_argument('--output',type=Path,default=Path('captures/batch-report-fresh.json'));a=p.parse_args()
 b=Bootstrap('https://rpc-robinhood.blockmachine.io',interval=.5);deadline=time.monotonic()+a.seconds;cases=[]
 async with websockets.connect('ws://127.0.0.1:19648') as ws:
  while time.monotonic()<deadline and len(cases)<a.count:
   try:frame=await asyncio.wait_for(ws.recv(),deadline-time.monotonic())
   except asyncio.TimeoutError:break
   outer=json.loads(frame);payload=json.loads(outer['raw']) if 'raw' in outer else outer
   for item in payload.get('messages',[]):
    if item['message']['message']['header']['kind']!=13:continue
    row=dict(kind='nitro_push',payload={'messages':[item]},recv_ns=time.time_ns(),mono_ns=time.monotonic_ns())
    proc=subprocess.run(['target/release/examples/decode_feed','--with-raw'],input=json.dumps(row)+'\n',text=True,capture_output=True,check=True)
    report=json.loads(proc.stdout.splitlines()[1]);f=dict(message=report)
    # A feed proposal may precede its executed block. This wait is validation
    # only; neither the decoder nor the follower waits on these requests.
    for attempt in range(6):
     h=b.rpc('eth_getBlockByHash',[report['block_hash'],False])
     if h:break
     await asyncio.sleep(.5)
    if not h:raise ValueError('executed block unavailable for research witness')
    f['header']=h
    for name in ('pre','diff'):
     cfg={'tracer':'prestateTracer'}
     if name=='diff':cfg['tracerConfig']={'diffMode':True}
     f[name]=b.rpc('debug_traceBlockByHash',[report['block_hash'],cfg])
    if len(f['pre'])!=2:raise ValueError('unexpected report transaction count')
    cases.append(f);a.output.write_text(json.dumps(cases));print('fresh report',report['sequence'],flush=True)
    if len(cases)>=a.count:break
 if not cases:raise SystemExit('no report observed within research window')
 print('saved',len(cases),'fixtures',flush=True)

if __name__=='__main__':asyncio.run(main())
