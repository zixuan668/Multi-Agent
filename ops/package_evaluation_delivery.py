"""Build a reviewable integrated source ZIP without credentials or artifacts."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from zipfile import ZipFile,ZIP_DEFLATED

ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--base',default='origin/feature/creative-agent',help='C补丁的B集成基线')
    args=p.parse_args()
    names=subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard','-z'],cwd=ROOT).decode().split('\0')
    allowed_env={'.env.example','.env.creative.example','.env.evaluation.example'}
    files=[]
    for name in sorted(set(names)):
        if not name:continue
        path=Path(name)
        if any(part in ('.git','.venv','node_modules','artifacts','__pycache__') for part in path.parts):continue
        if path.name.startswith('.env') and name not in allowed_env:continue
        if path.suffix in ('.pyc','.pem','.key','.log'):continue
        full=ROOT/path
        if full.is_file() and not full.is_symlink():files.append((name,full))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    manifest=[{'path':name,'sha256':hashlib.sha256(full.read_bytes()).hexdigest()} for name,full in files]
    with ZipFile(args.output,'w',ZIP_DEFLATED) as archive:
        for name,full in files:archive.write(full,'Multi-Agent/'+name)
        archive.writestr('Multi-Agent/delivery-manifest.json',json.dumps(manifest,ensure_ascii=False,indent=2))
        base=subprocess.check_output(['git','rev-parse',args.base],cwd=ROOT).decode().strip()
        patch=subprocess.check_output(['git','diff','--cached','--binary',base],cwd=ROOT)
        if patch:archive.writestr('C-changes.patch',patch)
        archive.writestr('PATCH-BASE.txt','Base commit: '+base+'\nApply C-changes.patch only after git apply --check on this B baseline.\nThe Multi-Agent folder contains the integrated source snapshot; extract to a new directory for review.\n')
    print(json.dumps({'archive':str(args.output.resolve()),'source_files':len(files),
                      'bytes':args.output.stat().st_size,'contains_credentials':False},ensure_ascii=False))
    return 0


if __name__=='__main__':raise SystemExit(main())
