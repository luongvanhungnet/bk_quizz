"""Respect partial Docling child coverage without changing frozen v5 files."""
import json
from pathlib import Path
import types
import zipfile


def install():
    import batch_layout
    if getattr(batch_layout,'_v3_coverage_adapter',False):return
    original=batch_layout.materialize

    def materialize(run,archive,packet,target=.05,maximum=.08):
        manifest_path=(Path(packet)/'manifest.json').resolve()
        original_load=original.__globals__['load'];pm=original_load(manifest_path)
        covered=set();has_child=False
        with zipfile.ZipFile(archive) as z:
            for name in z.namelist():
                if 'parser_candidates_' not in name or not name.endswith('.json'):continue
                envelope=json.loads(z.read(name))
                if envelope.get('status')!='ok':continue
                pages=envelope.get('covered_source_pages')
                if pages is None:covered.update(pm['page_map'].values())  # Legacy full-job envelope.
                else:
                    has_child=True
                    if not set(pages).issubset(pm['page_map'].values()):raise ValueError('Parser coverage outside parent packet')
                    covered.update(pages)
        if not has_child:return original(run,archive,packet,target,maximum)

        def scoped_load(path):
            value=original_load(path)
            if Path(path).resolve()==manifest_path:
                # Preserve the original file/hash and parent-local candidate indices.
                # Only parser-success coverage is narrowed; successful structure
                # records still add their own source pages independently.
                value={**value,'page_map':{k:v for k,v in value['page_map'].items() if v in covered}}
            return value

        scoped=types.FunctionType(original.__code__,{**original.__globals__,'load':scoped_load},
                                  original.__name__,original.__defaults__,original.__closure__)
        return scoped(run,archive,packet,target,maximum)

    batch_layout.materialize=materialize;batch_layout._v3_coverage_adapter=True
