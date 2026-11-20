"""Startup-only pinned code capture, kept separate from historical seeds."""
import json
from pathlib import Path
from bootstrap_state import Bootstrap,hashhex

def main():
 path=Path('reports/amm/router7627-code.json')
 if path.exists():raise ValueError('refuse to overwrite existing code checkpoint')
 b=Bootstrap('https://rpc-robinhood.blockmachine.io');h=b.rpc('eth_getBlockByNumber',['latest',False]);address='0x762750e704f33d864289ce3c242fb559bf9b02ee';code=b.rpc('eth_getCode',[address,h['number']]);verified=b.rpc('eth_getBlockByNumber',[h['number'],False])['hash']==h['hash']
 if not verified or code=='0x':raise ValueError('missing code or changed anchor')
 path.write_text(json.dumps(dict(anchor=h,address=address,code=code,code_hash=hashhex(bytes.fromhex(code[2:])),rpc_calls=b.calls,anchor_verified=verified,caveat='New pinned code only. No historical code identity or state parity; not merged into archived checkpoint.'),indent=2)+'\n');print(json.dumps(dict(anchor=h['number'],bytes=len(code[2:])//2,rpc_calls=b.calls)))
if __name__=='__main__':main()
