"""Build immutable app/base artifacts from a clean tagged Git commit."""
import argparse
import io
import json
from pathlib import Path
import subprocess
import zipfile

from bundle import ROOT, BASE_FILES, BASE_VERSION, application, manifest, sha256


def build(version):
    def git(*args):
        return subprocess.check_output(['git',*args],cwd=ROOT,text=True).strip()
    if git('status','--porcelain','--untracked-files=all'):
        raise ValueError('Commit all source changes before building a release')
    head=git('rev-parse','HEAD')
    if git('rev-parse','firmware-v'+version+'^{commit}')!=head:
        raise ValueError('Release tag must point to HEAD')
    subprocess.run(['make','check'],cwd=ROOT,check=True)
    app=application()
    m=manifest(app,head)
    if m['version']!=version:
        raise ValueError('APP_VERSION does not match tag')
    base={name:(ROOT/name).read_bytes() for name in BASE_FILES}
    base_metadata={'schema':1,'base_version':BASE_VERSION,'git_commit':head,
                   'files':{name:sha256(data) for name,data in base.items()},
                   'recovery_sha256':m['sha256']}
    encoded=(json.dumps(base_metadata,indent=2)+'\n').encode()
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as archive:
        files={**base,**{'recovery/'+n:d for n,d in app.items()},'base-manifest.json':encoded}
        for name,data in sorted(files.items()):
            item=zipfile.ZipInfo(name,(1980,1,1,0,0,0));item.compress_type=zipfile.ZIP_DEFLATED
            archive.writestr(item,data)
    artifacts={**app,'manifest.json':(json.dumps(m,indent=2)+'\n').encode(),
               'base-manifest.json':encoded,'base-firmware.zip':stream.getvalue()}
    out=ROOT/'.artifacts/releases'/version;out.mkdir(parents=True,exist_ok=True)
    for name,data in artifacts.items():
        path=out/name
        if path.exists() and path.read_bytes()!=data:
            raise ValueError('Refusing to overwrite release artifact: '+name)
        path.write_bytes(data)
    return out,tuple(artifacts)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('version');parser.add_argument('--publish',action='store_true')
    args=parser.parse_args()
    out,names=build(args.version)
    if args.publish:
        subprocess.run(['gh','release','create','firmware-v'+args.version,
                        *[str(out/name) for name in names],'--repo','nstielau/digirdu-lights',
                        '--verify-tag','--title','Digirdu firmware '+args.version,'--generate-notes'],check=True)
    print('Release artifacts: '+str(out))
