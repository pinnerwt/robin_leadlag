"""One-shot research export without stopping any recorder or deleting originals."""
import argparse,hashlib,json,shutil,time
from pathlib import Path
from snapshot_live_tape import snapshot

def digest(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()

def main():
    p=argparse.ArgumentParser();p.add_argument('output');p.add_argument('--cutoff-ns',required=True,type=int);a=p.parse_args()
    out=Path(a.output);out.mkdir(parents=True,exist_ok=False)
    manifest=dict(created_ns=time.time_ns(),cutoff_ns=a.cutoff_ns,files={},snapshots=[],iex_status=[])
    for source in sorted(Path('captures').glob('ohio-equity-*/events.bin.zst')):
        info=snapshot(source,out/(source.parent.name+'.bin.zst'),a.cutoff_ns);manifest['snapshots'].append(info)
        shutil.copyfile(source.parent/'status.json',out/(source.parent.name+'-status.json'))
    meta=json.load(open('reports/active-metric-capture.json'));directory=Path(meta['directory'])
    info=snapshot(directory/'raw.bin.zst',out/'robinhood.bin.zst',a.cutoff_ns);manifest['snapshots'].append(info)
    for name in ('capture.json','status.json','checkpoint-recovery.json'):
        shutil.copyfile(directory/name,out/('robinhood-'+name))
    for checkpoint in directory.glob('checkpoint-g*.json'):
        shutil.copyfile(checkpoint,out/checkpoint.name)
    for status in sorted(Path('captures').glob('ohio-iex-*/status.json')):
        data=json.load(open(status));manifest['iex_status'].append(data)
        if sum(data['counts'].values()) and (status.parent/'events.bin.zst').stat().st_size:
            info=snapshot(status.parent/'events.bin.zst',out/(status.parent.name+'.bin.zst'),a.cutoff_ns);manifest['snapshots'].append(info)
    for f in out.iterdir():
        if f.is_file():manifest['files'][f.name]=dict(size=f.stat().st_size,sha256=digest(f))
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(dict(directory=str(out),files=len(manifest['files']),bytes=sum(f['size'] for f in manifest['files'].values()))),flush=True)
if __name__=='__main__':main()
