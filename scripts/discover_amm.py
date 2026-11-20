"""Setup-only discovery. No discovery HTTP in the recorder hot path."""
import json,time,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def get(url):
 for i in range(5):
  try:
   with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'robin-leadlag-research/1'}),timeout=30) as r:return json.load(r)
  except Exception:
   if i==4:raise
   time.sleep(5*(i+1))
def main():
 cfg=json.loads((ROOT/'config/push.json').read_text());known={t.lower() for p in cfg['pools'] for t in p['tokens']};known.add('0x0000000000000000000000000000000000000000')
 rows={};sources=[]
 for page in range(1,6):
  url=f'https://api.geckoterminal.com/api/v2/networks/robinhood/pools?page={page}';data=get(url);sources.append(url)
  (ROOT/f'reports/amm/gecko-page-{page}.json').write_text(json.dumps(data))
  for p in data['data']:
   a=p['attributes'];rel=p['relationships'];tokens=[rel[k]['data']['id'].split('_',1)[1].lower() for k in ['base_token','quote_token']]
   row=dict(pool=a['address'].lower(),dex=rel['dex']['data']['id'],pair=a['name'],tokens=tokens,liquidity_usd=float(a['reserve_in_usd'] or 0),volume_24h_usd=float(a['volume_usd']['h24'] or 0))
   row['metric_tokens_match']=all(t in known for t in tokens)
   if row['volume_24h_usd']>=10000 and row['liquidity_usd']>=100000:rows[row['pool']]=row
  time.sleep(2)
 out=dict(chain_id=4663,asof_ns=time.time_ns(),sources=sources,selection='first five GeckoTerminal pool pages; volume >=10k and liquidity >=100k; not exhaustive',raw_capture='unfiltered existing Nitro/log tape',pools=sorted(rows.values(),key=lambda r:-r['volume_24h_usd']))
 (ROOT/'config/amm.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
if __name__=='__main__':main()
