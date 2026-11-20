"""End-to-end failure case: failed replacement must leave original feeds alive."""
import asyncio
import json
from pathlib import Path
import sys
import tempfile
import unittest
from websockets.asyncio.server import serve
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from tape import records

class RotationTest(unittest.IsolatedAsyncioTestCase):
    async def test_failed_warmup_keeps_old_links(self):
        peers={};connection_number=0;seq=0;halt=asyncio.Event()
        async def server(ws):
            nonlocal connection_number
            n=connection_number;connection_number+=1
            await ws.recv()
            if n>=3:
                await ws.send(json.dumps(dict(code=400,msg='injected replacement failure')))
                await ws.wait_closed();return
            await ws.send(json.dumps(dict(result=None,id=1)))
            q=asyncio.Queue();peers[n]=q
            try:
                while True:
                    try:row=await asyncio.wait_for(q.get(),.1)
                    except asyncio.TimeoutError:
                        if ws.close_code is not None:break
                        continue
                    await asyncio.sleep(n*.005)
                    await ws.send(json.dumps(row))
            except Exception:pass
            finally:peers.pop(n,None)
        async def publish():
            nonlocal seq
            while not halt.is_set():
                seq+=1
                row=dict(s='NVDABUSDT',u=seq,b=str(100+seq/1000),a=str(101+seq/1000),B='1',A='2')
                for q in peers.values():q.put_nowait(row)
                await asyncio.sleep(.04)
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)
            async with serve(server,'127.0.0.1',0) as srv:
                port=srv.sockets[0].getsockname()[1]
                config=dict(connections_per_venue=3,rotation_seconds=5,rotation_min_samples=5,rotation_warmup_seconds=2,duration_seconds=12,dedup_cache_entries=10000,feeds=[dict(venue='binance',url=f'ws://127.0.0.1:{port}',instruments={'NVDABUSDT':dict(ticker='NVDA',quote_currency='USDT')})])
                (path/'config.json').write_text(json.dumps(config))
                producer=asyncio.create_task(publish())
                with open(path/'events.bin','wb') as output:
                    process=await asyncio.create_subprocess_exec('target/release/examples/equity_capture',str(path/'config.json'),stdout=output,stderr=asyncio.subprocess.DEVNULL)
                    await asyncio.wait_for(process.wait(),20)
                self.assertEqual(process.returncode,0)
                halt.set();await producer
            rows=list(records([path/'events.bin']))
            self.assertTrue(any(r['kind']=='rotation_cancelled' for r in rows))
            self.assertFalse(any(r['kind']=='rotation_complete' for r in rows))
            quotes=[r for r in rows if r['kind']=='equity_bbo']
            ids=[r['update_id'] for r in quotes]
            self.assertGreater(len(ids),200)
            self.assertEqual(ids,list(range(ids[0],ids[-1]+1)))
            coverage=[r for r in rows if r['kind']=='equity_coverage'][-1]
            self.assertEqual({r['link'] for r in coverage['links'] if r['ready']},{0,1,2})
            self.assertEqual(rows[-1]['kind'],'equity_capture_end')
            self.assertIsNone(rows[-1]['failure'])

if __name__=='__main__':unittest.main()
