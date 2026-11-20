import asyncio
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from iex_capture import capture, exchange_ns
from tape import records
from websockets.asyncio.server import serve

class IexCaptureTest(unittest.IsolatedAsyncioTestCase):
    async def test_reconnect_and_binary_replay(self):
        connections = 0
        async def server(ws):
            nonlocal connections
            connections += 1
            auth = json.loads(await ws.recv())
            self.assertEqual(auth['key'], 'test-key')
            await ws.send(json.dumps([dict(T='success',msg='authenticated')]))
            subscription = json.loads(await ws.recv())
            self.assertEqual(subscription['quotes'], ['NVDA'])
            await ws.send(json.dumps([dict(T='subscription',quotes=['NVDA'])]))
            await ws.send(json.dumps([dict(T='q',S='NVDA',bp=100,ap=101,bs=2,**{'as':3},bx='V',ax='V',c=['R'],z='C',t='2026-11-19T14:30:00.123456789Z')]))
            if connections == 1:
                await ws.close()
            else:
                await ws.wait_closed()
        with tempfile.TemporaryDirectory() as temp:
            async with serve(server,'127.0.0.1',0) as s:
                port=s.sockets[0].getsockname()[1]
                config=dict(feed='test',url=f'ws://127.0.0.1:{port}',symbols=['NVDA'],disk_reserve_gib=0)
                directory=Path(temp)/'capture'
                status=await capture(config,dict(action='auth',key='test-key',secret='test-secret'),directory,3)
            rows=list(records([directory/'events.bin.zst']))
            quotes=[r for r in rows if r['kind']=='iex_bbo']
            self.assertGreaterEqual(len(quotes),2)
            self.assertNotEqual(quotes[0]['epoch'],quotes[1]['epoch'])
            self.assertEqual(quotes[0]['exchange_ns'],1795098600123456789)
            self.assertEqual(quotes[0]['bid_qty_lots'],2)
            self.assertTrue(status['finished'])
            self.assertFalse(status['connected'])
            self.assertNotIn('test-secret',json.dumps(rows))
            self.assertTrue(any(r['kind']=='iex_gap' for r in rows))

    def test_nanosecond_precision(self):
        self.assertEqual(exchange_ns('2026-11-19T14:30:00.123456789Z') % 10**9,123456789)
        self.assertEqual(exchange_ns('2026-11-19T14:30:00Z') % 10**9,0)

if __name__=='__main__':unittest.main()
