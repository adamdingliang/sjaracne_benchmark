#!/usr/bin/env python3
"""Publish compact DPI report assets without copying raw data or large sidecars.

Only report links/publication notes are adapted. Numeric tables and figures
are copied byte-for-byte; original and published SHA-256 values are recorded.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
from urllib.parse import unquote, urlsplit

LINK = re.compile(r'(\[[^\]\n]*\]\()([^\)\n]+)(\))')
EXCLUDED_TABLES = {'per_source_runs.tsv'}


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):
            h.update(block)
    return h.hexdigest()


def record(path):
    return {'bytes':Path(path).stat().st_size,'sha256':sha(path)}


def publish(source, destination, process, label, max_table_bytes=3_000_000, only=None):
    source=Path(source).resolve(strict=True)
    destination=Path(destination).resolve()
    process=Path(process).resolve(strict=True)
    if destination.exists():
        raise FileExistsError('Publication destination already exists: '+str(destination))
    chosen={}
    omitted=[]
    for path in sorted(source.iterdir()):
        if not path.is_file():
            continue
        if only and path.name not in only:
            omitted.append({'name':path.name,**record(path),'reason':'Not selected for this compact publication package'})
        elif path.name=='README.md':
            chosen[path.resolve()]='SOURCE_README.md'
        elif path.suffix.lower() in ('.md','.svg'):
            chosen[path.resolve()]=path.name
        elif path.suffix.lower()=='.tsv' and path.stat().st_size<=max_table_bytes and path.name not in EXCLUDED_TABLES:
            chosen[path.resolve()]=path.name
        elif path.suffix.lower()=='.json' and path.name!='analysis.json' and path.stat().st_size<1_000_000:
            chosen[path.resolve()]='original_'+path.name
        else:
            omitted.append({'name':path.name,**record(path),'reason':'Large/full analysis, per-source/per-edge records, or non-report artifact kept local'})
    chosen[process]='PROCESS.md'
    destination.mkdir(parents=True,exist_ok=False)
    adapted=[]
    records=[]
    for path,name in chosen.items():
        target=destination/name
        adaptations=[]
        if path.suffix.lower()=='.md':
            body=path.read_text(encoding='utf-8')
            def convert(match):
                raw=match.group(2)
                if raw.startswith(('http://','https://','mailto:','#','data:')):
                    return match.group(0)
                link=urlsplit(raw)
                relative=unquote(link.path)
                original=(path.parent/relative).resolve()
                if original in chosen:
                    converted=chosen[original]
                    if link.query:
                        converted+='?'+link.query
                    if link.fragment:
                        converted+='#'+link.fragment
                else:
                    converted='README.md#local-artifacts'
                if converted!=raw:
                    adaptations.append({'original_link':raw,'published_link':converted})
                return match.group(1)+converted+match.group(3)
            revised=LINK.sub(convert,body)
            note=('> Publication copy of a frozen local report/process. Scientific text and numbers are unchanged; '
                  'relative links are adapted to this compact package. See [publication provenance](PUBLICATION.json) '
                  'for original hashes and [local artifacts](README.md#local-artifacts) for omitted sidecars.\n\n')
            target.write_text(note+revised,encoding='utf-8',newline='\n')
        else:
            shutil.copyfile(path,target)
        records.append({'source_name':path.name,'published_name':name,'original':record(path),
                        'published':record(target),'link_adaptations':adaptations,
                        'scientific_content_changed':False})
        adapted.extend(adaptations)
    readme=['# '+label,'',
        'Compact publication package for a completed local benchmark. This does not rerun inference or change '
        'the scientific results. Tables and figures are byte-identical to their source files; Markdown '
        'publication copies add this provenance notice and adapt links only.','',
        '[Process](PROCESS.md) | [Publication manifest](PUBLICATION.json)','',
        '## Included results','']
    for item in records:
        if item['published_name'] not in ('PROCESS.md',):
            readme.append(f"- [{item['published_name']}]({item['published_name']})")
    readme+=['','## Local artifacts','',
        'Raw expression/reference matrices, native adjacency files/builds/environments, full analysis JSON '
        'and bulky per-source/per-edge sidecars remain in the original local evidence archive, not in Git. '
        'Links to unavailable sidecars in the frozen reports are redirected here explicitly, not replaced '
        'with invented data. Original report-provenance JSON is archived under `original_*` names and '
        'describes the original bundle, not the reduced publication package.','',
        'Original omitted-file hashes are listed below and in PUBLICATION.json. Existing dataset licensing '
        'and reference limitations still apply. No new data redistribution permission is implied.','']
    for item in omitted:
        readme.append(f"- `{item['name']}`: {item['bytes']:,} bytes; SHA-256 `{item['sha256']}`.")
    (destination/'README.md').write_text('\n'.join(readme)+'\n',encoding='utf-8',newline='\n')
    provenance={'schema':'dpi-compact-evidence-publication-v1','label':label,
                'published_utc':datetime.now(timezone.utc).isoformat(),
                'operation':'copy tables/figures unchanged; adapt Markdown links and add explicit publication notes',
                'source_result_directory':source.name,'process_source_name':process.name,
                'packager_sha256':sha(__file__),'files':records,'omitted_local_artifacts':omitted,
                'readme':record(destination/'README.md'),'new_scientific_run':False}
    (destination/'PUBLICATION.json').write_text(json.dumps(provenance,indent=2)+'\n',encoding='utf-8',newline='\n')
    verify(destination)
    return {'destination':str(destination),'published_files':len(records)+2,
            'bytes':sum(p.stat().st_size for p in destination.iterdir() if p.is_file()),'adapted_links':len(adapted)}


def verify(destination):
    destination=Path(destination).resolve(strict=True)
    data=json.loads((destination/'PUBLICATION.json').read_text(encoding='utf-8'))
    for item in data['files']:
        path=destination/item['published_name']
        if record(path)!=item['published']:
            raise ValueError('Publication hash mismatch: '+str(path))
        if path.suffix.lower()!='.md' and item['original']!=item['published']:
            raise ValueError('Numeric/figure/provenance artifact was changed')
    if record(destination/'README.md')!=data['readme']:
        raise ValueError('Publication README mismatch')
    for path in destination.glob('*.md'):
        for match in LINK.finditer(path.read_text(encoding='utf-8')):
            raw=match.group(2)
            if raw.startswith(('http://','https://','mailto:','#','data:')):
                continue
            target=(path.parent/unquote(urlsplit(raw).path)).resolve()
            if not target.is_file():
                raise ValueError('Broken publication link: '+str(path)+' -> '+raw)
    return True


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path)
    p.add_argument('--destination',type=Path,required=True)
    p.add_argument('--process',type=Path)
    p.add_argument('--label')
    p.add_argument('--include',action='append',default=[])
    p.add_argument('--verify',action='store_true')
    a=p.parse_args()
    if a.verify:
        verify(a.destination)
        print(json.dumps({'verified':str(a.destination)}))
    else:
        if a.source is None or a.process is None or not a.label:
            p.error('--source, --process and --label are required for publication')
        print(json.dumps(publish(a.source,a.destination,a.process,a.label,only=set(a.include) if a.include else None)))


if __name__=='__main__':
    main()
