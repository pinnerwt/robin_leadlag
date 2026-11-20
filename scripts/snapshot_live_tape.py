"""Export a fixed byte prefix of an active zstd tape, retaining complete frames only.
The original file and recorder are untouched. Never treats an active zstd tail as
proof of data completeness; records precise capture bounds in a sidecar manifest.
"""
import argparse
import json
from pathlib import Path
import struct
import subprocess
import threading
import time
from tape import MAGIC, MAX_FRAME, decode, write_record


def snapshot(source,output,cutoff_ns):
    source=Path(source);output=Path(output)
    limit=source.stat().st_size
    if output.exists():raise FileExistsError(output)
    dec=subprocess.Popen(['zstd','-q','-dc'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    errors=[]
    def feed():
        try:
            with source.open('rb') as f:
                remaining=limit
                while remaining:
                    chunk=f.read(min(1024*1024,remaining))
                    if not chunk:raise ValueError('source shrank during snapshot')
                    dec.stdin.write(chunk);remaining-=len(chunk)
        except BrokenPipeError:pass
        except Exception as exc:errors.append(str(exc))
        finally:dec.stdin.close()
    thread=threading.Thread(target=feed);thread.start()
    info=dict(source=str(source),source_bytes=limit,cutoff_ns=cutoff_ns,created_ns=time.time_ns(),records=0,last_recv_ns={},dropped_partial_tail=False,skipped_after_cutoff=0)
    try:
        with output.open('xb') as target:
            enc=subprocess.Popen(['zstd','-q','-T1','-c'],stdin=subprocess.PIPE,stdout=target)
            try:
                if dec.stdout.read(8)!=MAGIC:raise ValueError('missing binary header; tape may not have flushed yet')
                enc.stdin.write(MAGIC)
                while True:
                    header=dec.stdout.read(4)
                    if not header:break
                    if len(header)!=4:info['dropped_partial_tail']=True;break
                    n=struct.unpack('<I',header)[0]
                    if not 0<n<=MAX_FRAME:raise ValueError('invalid binary frame length')
                    frame=dec.stdout.read(n)
                    if len(frame)!=n:info['dropped_partial_tail']=True;break
                    row=decode(frame)
                    recv=row.get('recv_ns')
                    if recv is not None and recv>cutoff_ns:
                        info['skipped_after_cutoff']+=1;continue
                    enc.stdin.write(header+frame);info['records']+=1
                    if recv is not None:info['last_recv_ns'][row.get('kind','unknown')]=recv
                write_record(enc.stdin,dict(kind='snapshot_boundary',recv_ns=cutoff_ns,source_bytes=limit,active_source=True))
            finally:
                enc.stdin.close();status=enc.wait(timeout=30)
                if status:raise ValueError('snapshot compressor failed')
    finally:
        # Drain any decompressor tail so the bounded input writer cannot deadlock.
        while dec.stdout.read(65536):pass
        thread.join(timeout=30)
        message=dec.stderr.read().decode(errors='replace');code=dec.wait(timeout=30)
        dec.stdout.close();dec.stderr.close()
        info.update(source_zstd_exit=code,source_zstd_message=message.strip())
    if errors:raise RuntimeError(errors)
    if code and 'premature' not in message.lower() and 'unexpected end' not in message.lower():
        raise ValueError('corrupt source compressed stream: '+message)
    info['framing_complete']=not info['dropped_partial_tail']
    output.with_suffix(output.suffix+'.json').write_text(json.dumps(info,indent=2)+'\n')
    return info

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('source');p.add_argument('output');p.add_argument('--cutoff-ns',required=True,type=int);a=p.parse_args()
    print(json.dumps(snapshot(a.source,a.output,a.cutoff_ns)))
