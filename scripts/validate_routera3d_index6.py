"""Validate index-6 V4 intent and returned deltas, not settlement parity."""
import argparse,json,subprocess
from pathlib import Path
from routera3d_price import reverse_v3_limit
from v3_calldata import word,signed

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('seed');ap.add_argument('--settlement',action='store_true');a=ap.parse_args();cases=[]
    for exponent in [8,10,12,14]:
        subprocess.run(['python3','scripts/probe_routera3d_index6.py',a.seed,'--cap-exponent',str(exponent)]+(['--settlement-probe'] if a.settlement else []),check=True,capture_output=True,text=True)
        doc=json.loads(Path(f'reports/amm/routera3d-index6-probe-{exponent}{'-settlement' if a.settlement else ''}.json').read_text());r=doc['result']
        calls=[c for c in r['execution_calls'] if c['data'].startswith('0xf3cd914c')]
        assert len(calls)==1
        d=bytes.fromhex(calls[0]['data'][10:]);values=[word(d,i) for i in range(10)]
        assert values[:6]==[0,int('5fc5360d0400a0fd4f2af552add042d716f1d168',16),0x800000,1,int('987e330f00b79864a07fe81dfac344d0078abcc0',16),0]
        amount=65536<<exponent
        assert signed(values[6])==-amount
        assert values[7]==reverse_v3_limit(1900000000,10,40,10)
        assert values[8:]==[288,0]
        hooks=[x for x in r['execution_returns'] if x['selector']=='0x575e24b4']
        assert len(hooks)==2 and all(x['result']=='Return' for x in hooks)
        h=bytes.fromhex(hooks[0]['output'][2:])
        assert word(h,1)==0 and word(h,2)==0x400028
        swaps=[x for x in r['execution_returns'] if x['selector']=='0xf3cd914c']
        assert len(swaps)==1 and swaps[0]['result']=='Return'
        n=int(swaps[0]['output'],16);out=n>>128;delta1=(n&((1<<128)-1))-(1<<128)
        assert out>0 and delta1==-amount
        if a.settlement:
            assert not r['calls']
            frames=[x for x in r['execution_returns'] if x['selector']=='0x7782c562']
            assert len(frames)==2 and all(x['result']=='Return' for x in frames)
            unlock=[x for x in r['execution_returns'] if x['selector']=='0x48c89491']
            assert len(unlock)==1 and unlock[0]['result']=='Return'
            transfers=doc['synthetic_transfers'];assert len(transfers)==2
            assert int(transfers[0]['data'][-64:],16)==out
            assert int(transfers[1]['data'][-64:],16)==amount
            writes=[x for x in r['storage_writes'] if x['address']==doc['synthetic_storage'][0]['address'] and x['slot']==doc['synthetic_storage'][0]['slot']]
            assert len(writes)==1 and int(writes[0]['value'],16)==out
        else:
            assert any(c['data']=='0xd0e30db0' for c in r['calls'])
        cases.append(dict(exponent=exponent,input_usdg_raw=amount,output_native_raw=out,limit=values[7],hook_fee_ppm=40,swap_returned=True,settlement_frame_success=a.settlement,transaction_complete=False))
    Path('reports/amm/routera3d-index6'+('-settlement' if a.settlement else '')+'-validation.json').write_text(json.dumps(dict(cases=cases,matches=len(cases),
        caveat='Synthetic first V3 fill and balances; mixed-era child code; real archived manager/hook execution returns V4 deltas. Settlement variant uses real WETH deposit with synthetic initial child WETH zero, transfer replies and coherent balance replies. Final oracle absent. Not committed transaction state or historical parity.'),indent=2)+'\n')
    print(f'{len(cases)} cases match; settlement frame validated={a.settlement}; full transaction incomplete')

if __name__=='__main__':main()
