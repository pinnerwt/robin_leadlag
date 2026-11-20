"""Decompression-only relay; optional upstream receipt stamps for timing audits."""
import asyncio
import json
import sys
import time
import signal

PEERS=set()
from websockets.asyncio.client import connect
from websockets.asyncio.server import serve

async def relay(peer):
    PEERS.add(peer)
    try:
        async with connect('wss://feed.mainnet.chain.robinhood.com',
                           additional_headers={'Arbitrum-Feed-Client-Version':'2'},
                           max_size=32*1024*1024) as feed:
            async for msg in feed:
                if '--timestamp' in sys.argv:
                    msg=json.dumps(dict(relay_recv_ns=time.time_ns(),relay_mono_ns=time.monotonic_ns(),raw=msg),separators=(',',':'))
                await peer.send(msg)
    finally:
        PEERS.discard(peer)
        # Upstream failure must close downstream, so recorder writes a gap and reconnects.
        await peer.close()

async def main():
    port=int(sys.argv[1]) if len(sys.argv)>1 else 19647
    # Explicit local fault injection for recovery verification; server stays up.
    asyncio.get_running_loop().add_signal_handler(signal.SIGUSR1,lambda:[asyncio.create_task(p.close(code=1012,reason='local reconnect test'))for p in list(PEERS)])
    async with serve(relay,'127.0.0.1',port,compression=None):
        await asyncio.Future()

if __name__=='__main__':asyncio.run(main())
