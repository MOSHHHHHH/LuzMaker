"""Bootstrap historical service coverage from two trustworthy Open Bus snapshots.

The first snapshot is a baseline, not an invented change. Sampling the start of
our rolling month and yesterday recovers historical schedules but is NOT a full
daily publication history. Any detected change is dated at ingestion time.
Failure to access an archive is recorded explicitly; the official-feed build
can initialize normally. A malformed existing state is never silently reset.
"""
import argparse
import json
import shutil
import tempfile
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
try:
    from scripts.changes_pipeline import previous_month, run
except ModuleNotFoundError:
    from changes_pipeline import previous_month, run

BASE='https://openbus-stride-public.s3.eu-west-1.amazonaws.com/gtfs_archive/'


def bootstrap(state, output, today):
    state,output=Path(state),Path(output)
    if state.exists():
        return
    attempts=[]
    for day in sorted({previous_month(today), today-timedelta(days=1)}):
        url=BASE+day.strftime('%Y/%m/%d')+'/israel-public-transportation.zip'
        with tempfile.TemporaryDirectory(prefix='change-archive-') as tmp:
            path=Path(tmp)/'archive.zip'
            try:
                with urllib.request.urlopen(url,timeout=100) as response,path.open('wb') as f:
                    captured=response.headers.get('Last-Modified')
                    shutil.copyfileobj(response,f,1024*1024)
                # Every observation is stamped NOW, not at the unproven publication time.
                run(path,state,output,day,provenance={'url':url,'archiveDate':day.isoformat(),'lastModified':captured})
                attempts.append({'url':url,'status':'imported'})
            except Exception as exc:
                attempts.append({'url':url,'status':'unavailable','reason':str(exc)})
                print('Archive unavailable; preserving last valid observation:',url,repr(exc),flush=True)
    print(json.dumps({'archiveBootstrap':attempts},ensure_ascii=False),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--state',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    bootstrap(args.state,args.output,datetime.now(ZoneInfo('Asia/Jerusalem')).date())
