"""Read-only, pinned-block executor/funding/access preflight. Never used on signal hot path.
Requires a configured deployed executor; does not deploy, approve, or send transactions.
"""
import argparse,json,time
from pathlib import Path
from bootstrap_state import Bootstrap,selector,word,unpack,hashhex

def address(x):
    if isinstance(x,list):x='0x'+bytes(x).hex()
    if not isinstance(x,str) or len(x)!=42 or int(x,16)==0:raise ValueError('invalid address')
    return x.lower()

def check(c,b):
    head=b.rpc('eth_getBlockByNumber',['latest',False]);block=head['number'];rows={}
    wallets={address(s['policy']['wallet']) for s in c['stocks'].values()}
    executors={address(s['policy']['router']) for s in c['stocks'].values()}
    if len(wallets)!=1 or len(executors)!=1:raise ValueError('one wallet/executor required')
    wallet=wallets.pop();executor=executors.pop()
    def call(to,sig,args=()):
        return b.rpc('eth_call',[{'from':wallet,'to':to,'data':selector(sig)+b''.join(word(int(a,16) if isinstance(a,str) else a) for a in args).hex()},block])
    if int(b.rpc('eth_chainId',[]),16)!=4663:raise ValueError('wrong chain')
    if int(call(executor,'owner()'),16)!=int(wallet,16):raise ValueError('wrong executor owner')
    code=b.rpc('eth_getCode',[executor,block]);expected=c.get('executor_codehash')
    if not expected or hashhex(bytes.fromhex(code[2:])).lower()!=expected.lower():raise ValueError('explicit executor_codehash missing/mismatch')
    quote_tokens={address(s['quote_token']) for s in c['stocks'].values()}
    if len(quote_tokens)!=1:raise ValueError('one USDG required')
    quote=quote_tokens.pop();cash=int(call(quote,'balanceOf(address)',[wallet]),16)
    quote_allowance=int(call(quote,'allowance(address,address)',[wallet,executor]),16)
    for ticker,s in c['stocks'].items():
        pool=address(s['policy']['pool']);base=address(s['base_token'])
        imm=unpack(call(pool,'getImmutables()'))
        if len(imm)!=24 or imm[1:3]!=[int(base,16),int(quote,16)]:raise ValueError(f'{ticker}: token order mismatch')
        codehash=hashhex(bytes.fromhex(b.rpc('eth_getCode',[pool,block])[2:]))
        binding=unpack(call(executor,'pools(address)',[pool]))
        if binding!=[int(base,16),int(quote,16),1,int(codehash,16)]:raise ValueError(f'{ticker}: executor binding mismatch')
        # Nonzero tx.origin plus pool's SWAP guard exercises oracle pool registration/blacklist.
        prices=unpack(call(pool,'getSellAndBuyPrices()'))
        if len(prices)!=2 or not 0<prices[0]<=prices[1]:raise ValueError(f'{ticker}: live access/price check failed')
        rows[ticker]={'base':str(int(call(base,'balanceOf(address)',[wallet]),16)),
                      'base_allowance':str(int(call(base,'allowance(address,address)',[wallet,executor]),16)),
                      'pool_codehash':codehash,'provider_access_verified':True}
    nonce=int(b.rpc('eth_getTransactionCount',[wallet,block]),16)
    pending=int(b.rpc('eth_getTransactionCount',[wallet,'pending']),16)
    if nonce!=pending:raise ValueError('unresolved pending nonce; reconcile before admission')
    native=int(b.rpc('eth_getBalance',[wallet,block]),16)
    if b.rpc('eth_getBlockByNumber',[block,False])['hash']!=head['hash']:raise ValueError('anchor reorg')
    return {'phase':'startup_only','anchor':head,'wallet':wallet,'executor':executor,'executor_codehash':expected,
            'nonce':nonce,'cash':str(cash),'native':str(native),'quote_allowance':str(quote_allowance),'stocks':rows,
            'observed_ns':time.time_ns(),'note':'Pinned historical state; push catch-up required before admission. No exchange hedge verification.'}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',type=Path,required=True);p.add_argument('--rpc',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    result=check(json.loads(a.config.read_text()),Bootstrap(a.rpc));a.output.write_text(json.dumps(result,indent=2)+'\n')
if __name__=='__main__':main()
