"""Bounded public-feed probes using real wscat in a pseudo-terminal."""
import concurrent.futures,json,os,pty,select,subprocess,time,re
from pathlib import Path
symbols=['ETHUSDT','SPCXBUSDT','METABUSDT','TSLABUSDT','GOOGLBUSDT','NVDABUSDT','AAPLBUSDT','MUBUSDT','SPYBUSDT','QQQBUSDT','INTCBUSDT']
binance=json.dumps({'method':'SUBSCRIBE','params':[s.lower()+'@bookTicker' for s in symbols],'id':1})
kraken=json.dumps({'method':'subscribe','params':{'channel':'ticker','symbol':['NVDAx/USD','METAx/USD','AAPLx/USD','SPCXx/USD'],'event_trigger':'bbo'}})
probes=[('binance443','wss://stream.binance.com:443/ws',binance),('binance9443','wss://stream.binance.com:9443/ws',binance),('binance_marketdata','wss://data-stream.binance.vision/ws',binance),('kraken','wss://ws.kraken.com/v2',kraken)]
probes.extend([
 ('coinbase_intx','wss://ws-md.international.coinbase.com',json.dumps(dict(type='SUBSCRIBE',product_ids=['NVDA-PERP','META-PERP','SPCX-PERP'],channels=['LEVEL1']))),
 ('bybit','wss://stream.bybit.com/v5/public/spot',json.dumps(dict(op='subscribe',args=['orderbook.1.NVDAXUSDT','orderbook.1.METAXUSDT','orderbook.1.SPCXXUSDT'])))
])
def run(item):
 name,url,message=item
 master,slave=pty.openpty();started=time.time_ns()
 command=['wscat','--no-color','-c',url,'-x',message,'-w','10']
 p=subprocess.Popen(command,stdin=slave,stdout=slave,stderr=slave,close_fds=True);os.close(slave);chunks=[]
 try:
  end=time.monotonic()+18
  while time.monotonic()<end:
   if select.select([master],[],[],.2)[0]:
    try:chunk=os.read(master,65536)
    except OSError:break
    if not chunk:break
    chunks.append(chunk)
   elif p.poll() is not None:break
 finally:
  if p.poll() is None:p.terminate()
  p.wait(timeout=5);os.close(master)
 output=re.sub(r'\x1b\[[0-9;?]*[A-Za-z]','',b''.join(chunks).decode(errors='replace'))
 return dict(name=name,url=url,command=command,started_ns=started,exit_code=p.returncode,output=output)
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(run,probes))
Path('reports/ohio-wscat-probes.json').write_text(json.dumps(results,indent=2)+'\n')
for row in results:print(json.dumps(dict(name=row['name'],exit_code=row['exit_code'],output=row['output'][:6000])))
