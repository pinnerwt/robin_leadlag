"""Startup-only public wallet funding check; no credentials or transactions."""
import argparse
import asyncio
import json
import time
from decimal import Decimal
from pathlib import Path
import websockets

async def check(url, wallet, baseline):
    scaled = Decimal(baseline) * 10**18
    if not scaled.is_finite() or scaled <= 0 or scaled != scaled.to_integral_value():
        raise ValueError("invalid baseline quantity")
    if len(wallet) != 42 or not wallet.startswith('0x'):
        raise ValueError('invalid wallet')
    int(wallet[2:], 16)
    async with websockets.connect(url, open_timeout=15) as ws:
        sequence = 0
        async def rpc(method, params):
            nonlocal sequence
            sequence += 1
            await ws.send(json.dumps(dict(jsonrpc='2.0', id=sequence, method=method, params=params)))
            response = json.loads(await asyncio.wait_for(ws.recv(), 20))
            if response.get('id') != sequence or 'error' in response:
                raise ValueError(f'{method}: invalid RPC response: {response.get("error")}')
            return response['result']
        if int(await rpc('eth_chainId', []), 16) != 4663:
            raise ValueError('wrong chain')
        anchor = await rpc('eth_getBlockByNumber', ['latest', False])
        block = anchor['number']
        result = dict(wallet=wallet, block=block, block_hash=anchor['hash'], checked_ns=time.time_ns())
        for name, token in [('weth', '0x0bd7d308f8e1639fab988df18a8011f41eacad73'),
                            ('usdg', '0x5fc5360d0400a0fd4f2af552add042d716f1d168')]:
            raw = int(await rpc('eth_call', [{'to':token, 'data':'0x70a08231'+wallet[2:].zfill(64)}, block]), 16)
            result[name+'_raw'] = str(raw)
        result['native_raw'] = str(int(await rpc('eth_getBalance', [wallet, block]), 16))
        result['nonce'] = int(await rpc('eth_getTransactionCount', [wallet, block]), 16)
        result['pending_nonce'] = int(await rpc('eth_getTransactionCount', [wallet, 'pending']), 16)
        if (await rpc('eth_getBlockByNumber', [block, False]))['hash'] != anchor['hash']:
            raise ValueError('anchor changed')
        result['baseline_matches'] = int(result['weth_raw']) == int(scaled)
        result['cash_sufficient'] = int(result['usdg_raw']) >= 100_000_000
        result['has_native_gas'] = int(result['native_raw']) > 0
        result['nonce_clear'] = result['nonce'] == result['pending_nonce']
        result['scope'] = 'startup funding only; not permission to trade or proof of pool state'
        return result

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--wallet', required=True)
    p.add_argument('--baseline', required=True)
    p.add_argument('--url', default='wss://rpc-robinhood.blockmachine.io')
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    result = asyncio.run(check(a.url, a.wallet, a.baseline))
    a.output.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result))
