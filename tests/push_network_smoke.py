"""Local mock: assert subscription-only wire traffic and multi-link dedup."""
import asyncio
import json
from pathlib import Path
import sys
import tempfile
import time
from websockets.asyncio.server import serve
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from tape import records

async def main():
    requests=[]
    config=json.loads((ROOT/'config/push.json').read_text())
    async def handle(ws):
        if ws.request.path=='/chain':
            for _ in range(2):
                request=json.loads(await ws.recv());requests.append(request)
                await ws.send(json.dumps(dict(jsonrpc='2.0',id=request['id'],result=str(request['id']))))
        elif ws.request.path=='/feed':
            await ws.send(json.dumps(dict(relay_recv_ns=time.time_ns(),relay_mono_ns=time.monotonic_ns(),raw=json.dumps(dict(messages=[],version=1)))))
        else:
            for s in config['symbols']:
                for seq in (100,99,100,101):
                    await ws.send(json.dumps(dict(stream=s.lower()+'@bookTicker',data=dict(s=s,u=seq,b='100.000',a='101.000',B='2.0',A='3.0'))))
        await ws.wait_closed()
    async with serve(handle,'127.0.0.1',0) as server:
        port=server.sockets[0].getsockname()[1]
        config.update(feed_url=f'ws://127.0.0.1:{port}/feed',logs_url=f'ws://127.0.0.1:{port}/chain',binance_base=f'ws://127.0.0.1:{port}/binance?streams=')
        with tempfile.TemporaryDirectory() as directory:
            directory=Path(directory);path=directory/'config.json';path.write_text(json.dumps(config))
            tape=directory/'test.bin'
            with tape.open('wb') as output:
                proc=await asyncio.create_subprocess_exec(str(ROOT/'target/release/examples/push_capture'),str(path),'1',stdout=output,stderr=asyncio.subprocess.PIPE)
                _,err=await proc.communicate()
                assert proc.returncode==0,err.decode()
            rows=list(records([tape]))
    assert [r['method'] for r in requests]==['eth_subscribe','eth_subscribe'],requests
    assert [r['params'][0] for r in requests]==['logs','newHeads']
    bbo=[r for r in rows if r['kind']=='bbo']
    assert len(bbo)==22,len(bbo)
    assert set(r['symbol'] for r in bbo)==set(config['symbols'])
    assert rows[-1]['kind']=='capture_end' and rows[-1]['complete']
    assert next(r for r in rows if r['kind']=='nitro_push')['relay_recv_ns']>0
    print('PASS: only 2 subscription requests; 3 Binance links dedup to 22 updates / 11 symbols; relay receipt stamps preserved')

asyncio.run(main())
