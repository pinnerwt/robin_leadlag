"""Supervise Rust spot-token recorder; compress binary directly, inspect only coverage."""
import argparse
import datetime
import json
import os
from pathlib import Path
import selectors
import shutil
import signal
import subprocess
import time


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--config',default='config/equity-ohio.json')
    ap.add_argument('--directory')
    ap.add_argument('--seconds',type=int)
    a=ap.parse_args()
    config=json.load(open(a.config))
    seconds=a.seconds or config['duration_seconds']
    reserve=config['disk_reserve_gib']*1024**3
    if shutil.disk_usage('.').free < reserve:raise RuntimeError('disk reserve reached; no files deleted')
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    directory=Path(a.directory or 'captures/ohio-equity-'+stamp)
    directory.mkdir(parents=True,exist_ok=False)
    (directory/'config.json').write_text(json.dumps(config,indent=2)+'\n')
    status=dict(pid=os.getpid(),started_ns=time.time_ns(),directory=str(directory),finished=False,error=None,
                config=config,coverage=None,kind='equity_token_and_crypto_spot_only')
    reports=Path('reports');reports.mkdir(exist_ok=True)
    active=reports/'active-equity-capture.json';tmp=active.with_suffix('.tmp');tmp.write_text(json.dumps(status,indent=2)+'\n');tmp.replace(active)
    stop=False
    def terminate(*_):
        nonlocal stop
        stop=True
    signal.signal(signal.SIGTERM,terminate);signal.signal(signal.SIGINT,terminate)
    def save():
        status['updated_ns']=time.time_ns()
        tmp=directory/'status.tmp';tmp.write_text(json.dumps(status,indent=2)+'\n');tmp.replace(directory/'status.json')
    with open(directory/'events.bin.zst','xb') as tape, open(directory/'capture.log','wb') as log:
        compressor=subprocess.Popen(['zstd','-q','-T1','-c'],stdin=subprocess.PIPE,stdout=tape)
        capture=subprocess.Popen(['target/release/examples/equity_capture',a.config,str(seconds)],stdout=compressor.stdin,stderr=subprocess.PIPE)
        status.update(capture_pid=capture.pid,compressor_pid=compressor.pid)
        compressor.stdin.close()
        sel=selectors.DefaultSelector();sel.register(capture.stderr,selectors.EVENT_READ)
        buf=b'';last_save=0
        try:
            while capture.poll() is None:
                if stop:
                    capture.terminate();break
                if time.monotonic()-last_save>5:
                    if shutil.disk_usage(directory).free < reserve:raise RuntimeError('disk reserve reached')
                    if compressor.poll() is not None:raise RuntimeError('compressor stopped')
                    save();last_save=time.monotonic()
                if not sel.select(1):continue
                chunk=os.read(capture.stderr.fileno(),65536)
                if not chunk:break
                log.write(chunk);log.flush();buf+=chunk
                while b'\n' in buf:
                    line,buf=buf.split(b'\n',1)
                    try:row=json.loads(line)
                    except ValueError:continue
                    if row.get('kind')=='equity_coverage':status['coverage']=row
            capture.wait(timeout=30)
            if capture.returncode:raise RuntimeError('recorder exited '+str(capture.returncode))
        except Exception as exc:
            status['error']=str(exc)
        finally:
            if capture.poll() is None:
                capture.terminate()
                try:capture.wait(timeout=30)
                except subprocess.TimeoutExpired:capture.kill();capture.wait()
            try:compressor.wait(timeout=30)
            except subprocess.TimeoutExpired:compressor.kill();compressor.wait()
            if compressor.returncode and not status['error']:status['error']='compressor failed'
            status.update(finished=True,capture_exit=capture.returncode,compressor_exit=compressor.returncode)
            save()
    if status['error']:raise RuntimeError(status['error'])

if __name__=='__main__':main()
