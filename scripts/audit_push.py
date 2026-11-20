"""Audit raw push capture coverage. Does not assert state/execution completeness."""
import argparse
from collections import Counter
import json
from tape import records

FEED='0x29e088dffd7bf6815d088137a59f364d6747163baa7ff4bc47f316a1ad1b9586'
LP_ADD='0xa55772434bee2a347743b1e8086fa44bac69a060e124ec92ab6b9cc7fc5268af'
LP_REMOVE='0xf53d04bdbda6d88dd536895ec533833d3e09d0cbe2474fae32a368c5f83fc610'

def audit(paths):
    counts=Counter(); symbols=Counter(); pools={}; pool_counts=Counter(); feeds=Counter()
    expected=set(); gaps=Counter(); previous_sequence=None; previous_head=None; last_ids={}
    first=None; last=None; sessions=0; clean_ends=0; order=0; last_mono=None
    for row in records(paths):
        kind=row['kind'];counts[kind]+=1
        if kind=='session':
            sessions+=1;previous_sequence=None;previous_head=None;last_ids={};last_mono=None
            expected.update(row['symbols']);pools.update({r['pool'].lower():r for r in row['pools']})
        if 'recv_ns' in row:
            first=row['recv_ns'] if first is None else min(first,row['recv_ns']);last=max(last or 0,row['recv_ns'])
        if 'mono_ns' in row:
            order+=int(last_mono is not None and row['mono_ns']<last_mono);last_mono=row['mono_ns']
        if kind=='gap':gaps['transport_'+row['stream']]+=1
        if kind=='capture_end':clean_ends+=int(row['complete'])
        if kind=='bbo':
            s=row['symbol'];symbols[s]+=1
            if s in last_ids and row['update_id']<=last_ids[s]:gaps['nonincreasing_bbo']+=1
            last_ids[s]=row['update_id']
        if kind=='head':
            h=row['payload']
            if previous_head and (int(h['number'],16)!=int(previous_head['number'],16)+1 or h['parentHash']!=previous_head['hash']):gaps['head_discontinuity']+=1
            previous_head=h
        if kind=='nitro_push':
            for item in row['payload'].get('messages',[]):
                sequence=item['sequenceNumber']
                if previous_sequence is not None and sequence!=previous_sequence+1:gaps['nitro_sequence_discontinuity']+=1
                previous_sequence=sequence
        if kind=='chain_log':
            log=row['payload'];address=log['address'].lower();topics=log.get('topics',[])
            if log.get('removed'):gaps['removed_log']+=1
            if address in pools:
                pool_counts[address]+=1
                if topics and topics[0] in (LP_ADD,LP_REMOVE):counts['pool_liquidity_add' if topics[0]==LP_ADD else 'pool_liquidity_remove']+=1
            if topics and topics[0]==FEED:feeds[address+':'+topics[1]]+=1
    return dict(sessions=sessions,clean_ends=clean_ends,duration_seconds=(last-first)/1e9 if first is not None else 0,
                counts=counts,binance_counts=symbols,missing_symbols=sorted(expected-symbols.keys()),
                pool_count=len(pools),pools_with_events=len(pool_counts),
                pool_events=[dict(pool=a,pair=r['pair'],events=pool_counts[a],binance_symbol=r['binance_symbol']) for a,r in pools.items()],
                unsupported_binance_pairs=sorted({r['pair'] for r in pools.values() if r['binance_symbol'] is None}),
                feed_counts=feeds,discontinuities=gaps,arrival_order_inversions=order,
                state_complete=False,quote_status='unavailable: missing verified initial state and full provider/extension execution',
                note='Zero discontinuities does not prove complete logs; public subscriptions have no block-complete proof.')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('tapes',nargs='+');a=p.parse_args()
    print(json.dumps(audit(a.tapes),indent=2))
