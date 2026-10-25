"""Audit the actual downloaded OCR alphabet, including decomposed Unicode."""
import argparse
import unicodedata
from pathlib import Path
import yaml
from common import digest, dump_json


def run(out, config):
    raw=config.read_bytes()
    chars=set(yaml.safe_load(raw.decode('utf-8'))['PostProcess']['character_dict'])
    probes='ăâđêôơưàáảãạằắẳẵặầấẩẫậèéẻẽẹềếểễệìíỉĩịòóỏõọồốổỗộờớởỡợùúủũụừứửữựỳýỷỹỵ'
    missing=[c for c in probes if c not in chars and not all(v in chars for v in unicodedata.normalize('NFD',c))]
    audit={'model':'latin_PP-OCRv5_mobile_rec','config_path':str(config),'config_sha256':digest(raw),
           'alphabet_size':len(chars),'vietnamese_probe_characters':probes,
           'unsupported_vietnamese_characters':missing,'complete_for_probes':not missing,
           'training_policy':'OCR output is a hypothesis; source-verified native text/reviewed transcripts are the training layer.'}
    dump_json(out/'ocr_capabilities.json',audit)
    print(f'OCR alphabet audit: {len(missing)} Vietnamese probe characters unsupported; see ocr_capabilities.json')


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--config',type=Path,default=Path.home()/'.paddlex/official_models/latin_PP-OCRv5_mobile_rec/inference.yml')
    a=p.parse_args()
    run(a.out,a.config)
