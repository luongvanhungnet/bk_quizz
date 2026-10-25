"""Bounded, resumable OCR evidence collection; never writes review decisions."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import Counter
import csv
import gzip
import hashlib
import io
import json
import math
import os
from pathlib import Path
import queue
import re
import signal
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import uuid

VERSION = "sft-ocr-probe-v3"
WIRE_PREFIX = "__BKQUIZ_OCR_RESULT_V1__\t"
DEFAULT_TESSERACT = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")


def canonical(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False)


def sha(path):
    with Path(path).open("rb") as stream:return hashlib.file_digest(stream,"sha256").hexdigest()


def atomic_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_name(path.name+"."+uuid.uuid4().hex+".partial")
    try:
        temporary.write_text(canonical(value)+"\n",encoding="utf-8")
        for attempt in range(40):
            try:temporary.replace(path);return
            except PermissionError:
                if attempt==39:raise
                time.sleep(.05)
    finally:temporary.unlink(missing_ok=True)


def read_jsonl(path):
    with Path(path).open(encoding="utf-8-sig") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def parse_tsv(tsv,width,height):
    """Preserve words/line order and compute observed OCR confidence summaries."""
    header=tsv.splitlines()[0].split("\t") if tsv.strip() else []
    required={"level","page_num","block_num","par_num","line_num","left","top","width","height","conf","text"}
    if not required.issubset(header):
        raise ValueError("Tesseract did not return the required TSV header")
    words=[];lines=[];current_key=None;current=[]
    for row in csv.DictReader(io.StringIO(tsv),delimiter="\t",quoting=csv.QUOTE_NONE):
        if row.get("level")!="5":continue
        text=row.get("text","").strip()
        try:confidence=float(row.get("conf","-1"))
        except ValueError:continue
        if not text or not math.isfinite(confidence) or confidence<0:continue
        try:box=[int(row[k]) for k in ["left","top","width","height"]]
        except (KeyError,ValueError):continue
        word={"text":text,"confidence":round(confidence,3),"bbox":box}
        words.append(word)
        key=tuple(row.get(k,"") for k in ["page_num","block_num","par_num","line_num"])
        if current_key is not None and key!=current_key:
            lines.append(" ".join(current));current=[]
        current_key=key;current.append(text)
    if current:lines.append(" ".join(current))
    confidences=sorted(w["confidence"] for w in words)
    weight=sum(len(w["text"]) for w in words)
    quantile=lambda q:confidences[min(len(confidences)-1,int((len(confidences)-1)*q))] if confidences else None
    result={"text":"\n".join(lines),"words":words,"word_count":len(words),"character_count":weight,
            "weighted_confidence":round(sum(w["confidence"]*len(w["text"]) for w in words)/weight,3) if weight else None,
            "mean_confidence":round(sum(confidences)/len(confidences),3) if confidences else None,
            "confidence_p10":quantile(.1),"confidence_p50":quantile(.5),"confidence_p90":quantile(.9),
            "word_fraction_conf_ge80":round(sum(c>=80 for c in confidences)/len(confidences),4) if confidences else 0,
            "word_fraction_conf_ge60":round(sum(c>=60 for c in confidences)/len(confidences),4) if confidences else 0,
            "word_fraction_conf_lt40":round(sum(c<40 for c in confidences)/len(confidences),4) if confidences else 0,
            "ocr_bbox_area_fraction":round(min(1.,sum(w["bbox"][2]*w["bbox"][3] for w in words)/max(1,width*height)),5),
            "tsv_sha256":hashlib.sha256(tsv.encode("utf-8")).hexdigest()}
    text=result["text"]
    nonspace=[c for c in text if not c.isspace()]
    result["alphanumeric_fraction"]=round(sum(c.isalnum() for c in nonspace)/max(1,len(nonspace)),4)
    result["line_count"]=len(lines)
    return result


def image_metrics(image):
    import cv2
    import numpy as np
    gray=image if image.ndim==2 else cv2.cvtColor(image,cv2.COLOR_BGR2GRAY)
    height,width=gray.shape
    mask=(gray<210).astype("uint8")
    count,_,stats,_=cv2.connectedComponentsWithStats(mask,8)
    glyphs=[s for s in stats[1:] if 2<=s[cv2.CC_STAT_AREA]<=3000 and 2<=s[cv2.CC_STAT_HEIGHT]<=90 and 1<=s[cv2.CC_STAT_WIDTH]<=120]
    heights=[int(s[cv2.CC_STAT_HEIGHT]) for s in glyphs]
    active=(mask.sum(axis=1)>max(2,width*.003)).astype("uint8")
    transitions=int(np.sum((active[1:]==1)&(active[:-1]==0)))+int(active[0])
    return {"width":width,"height":height,"pixels":width*height,
            "ink_fraction":round(float(mask.mean()),6),"gray_mean":round(float(gray.mean()),3),
            "gray_std":round(float(gray.std()),3),"contrast_p95_p05":round(float(np.percentile(gray,95)-np.percentile(gray,5)),3),
            "laplacian_variance":round(float(cv2.Laplacian(gray,cv2.CV_64F).var()),3),
            "connected_components":count-1,"glyph_like_components":len(glyphs),
            "median_glyph_height":float(np.median(heights)) if heights else None,
            "small_glyph_fraction":round(sum(h<8 for h in heights)/len(heights),4) if heights else 0,
            "active_row_fraction":round(float(active.mean()),5),"ink_row_runs":transitions}


def ocr_ink_metrics(image,words,padding=3):
    """Measure visible dark pixels explained by OCR boxes; never infer semantics.

    A high value alone cannot establish that a figure/formula was transcribed.
    A low value prevents text-only routing from silently discarding visible ink.
    """
    import cv2
    import numpy as np
    gray=image if image.ndim==2 else cv2.cvtColor(image,cv2.COLOR_BGR2GRAY)
    height,width=gray.shape
    ink=gray<210
    covered=np.zeros((height,width),dtype=bool)
    for word in words:
        left,top,box_width,box_height=word["bbox"]
        x0,y0=max(0,left-padding),max(0,top-padding)
        x1,y1=min(width,left+box_width+padding),min(height,top+box_height+padding)
        if x1>x0 and y1>y0:covered[y0:y1,x0:x1]=True
    count=int(ink.sum());outside=int(np.count_nonzero(ink&~covered))
    return {"ocr_ink_coverage":round((count-outside)/count,6) if count else 1.,
            "uncovered_ink_fraction":round(outside/max(1,width*height),6),
            "uncovered_ink_pixels":outside,"ocr_box_padding_pixels":padding}


def render_preview(page,destination,max_edge):
    """Rasterize the exact catalog clip, using Poppler for known MuPDF stalls."""
    import pymupdf
    source=Path(page["source_path"])
    if sha(source)!=page["source_sha256"]:raise ValueError("Original PDF hash changed")
    box=page["bbox"]
    with pymupdf.open(source) as document:
        pdf_page=document[page["page"]-1];clip=pymupdf.Rect(box)
        rect=pdf_page.rect
        if (not clip.is_valid or clip.is_empty or clip.x0<rect.x0-.01 or clip.y0<rect.y0-.01
                or clip.x1>rect.x1+.01 or clip.y1>rect.y1+.01):raise ValueError("Invalid source clip")
        clip=clip&rect
        scale=min(3.,max_edge/max(clip.width,clip.height))
        if "extraction_timeout" in page.get("reasons",[]):
            from review_render import find_pdftoppm
            binary=find_pdftoppm()
            if not binary:raise RuntimeError("No Poppler binary for long PDF")
            command=[binary,"-f",str(page["page"]),"-singlefile","-r",str(72*scale),
                     "-x",str(math.floor(clip.x0*scale)),"-y",str(math.floor(clip.y0*scale)),
                     "-W",str(math.ceil(clip.width*scale)),"-H",str(math.ceil(clip.height*scale)),
                     "-gray","-png",str(source),str(destination.with_suffix(""))]
            result=subprocess.run(command,capture_output=True,timeout=30)
            if result.returncode:raise RuntimeError(result.stderr.decode("utf-8",errors="replace")[-1000:])
        else:
            pix=pdf_page.get_pixmap(matrix=pymupdf.Matrix(scale,scale),clip=clip,colorspace=pymupdf.csGRAY,alpha=False,annots=True)
            pix.save(destination)
    if sha(source)!=page["source_sha256"]:raise ValueError("Original PDF changed during preview")


def tesseract_tsv(image,tesseract,tessdata,psm,timeout):
    environment=os.environ.copy();environment["OMP_THREAD_LIMIT"]="1";environment["OMP_NUM_THREADS"]="1"
    # A models-only tessdata directory has no configs/tsv file. Set the output
    # parameter directly; a missing config otherwise yields plaintext and exit0.
    result=subprocess.run([str(tesseract),str(image),"stdout","--tessdata-dir",str(tessdata),"-l","vie+eng","--psm",str(psm),"-c","tessedit_create_tsv=1"],
                          capture_output=True,timeout=timeout,env=environment,
                          creationflags=subprocess.CREATE_NO_WINDOW if os.name=="nt" else 0)
    if result.returncode:raise RuntimeError("Tesseract failed (exit "+str(result.returncode)+"): "+result.stderr.decode("utf-8",errors="replace")[-1000:])
    return result.stdout.decode("utf-8-sig",errors="replace")


def worker(request):
    import cv2
    cv2.setNumThreads(1)
    page=request["page"];config=request["config"]
    with tempfile.TemporaryDirectory(dir=request["temp_root"],prefix="probe_") as temporary:
        image=Path(temporary)/"preview.png"
        render_preview(page,image,config["max_edge"])
        pixels=cv2.imread(str(image),cv2.IMREAD_GRAYSCALE)
        if pixels is None:raise RuntimeError("Preview PNG could not be read")
        quality=image_metrics(pixels);variants=[]
        native_chars=len(re.sub(r"\s","",page.get("native_text_preview","")))
        if quality["ink_fraction"]<.001 and quality["gray_std"]<4 and native_chars<20:
            return {"status":"blank_candidate","image_metrics":quality,"preview_sha256":sha(image),
                    "ocr":parse_tsv("level\tpage_num\tblock_num\tpar_num\tline_num\tleft\ttop\twidth\theight\tconf\ttext\n",quality["width"],quality["height"]),
                    "variants":[],"reason":"Extremely low ink and contrast; not a human review decision"}
        try:
            first=tesseract_tsv(image,config["tesseract"],config["tessdata"],3,config["ocr_timeout"])
            parsed=parse_tsv(first,quality["width"],quality["height"]);parsed["psm"]=3
        except Exception as error:
            return {"status":"error","error_phase":"ocr","error_type":type(error).__name__,"error":str(error),
                    "image_metrics":quality,"preview_sha256":sha(image)}
        variants.append(parsed)
        if (config["retry"] and quality["ink_fraction"]>.002
                and (parsed["word_count"]<8 or (parsed["weighted_confidence"] or 0)<45)):
            try:
                alternate=tesseract_tsv(image,config["tesseract"],config["tessdata"],11,config["ocr_timeout"])
                other=parse_tsv(alternate,quality["width"],quality["height"]);other["psm"]=11;variants.append(other)
            except Exception as error:
                # A secondary engine crash must not erase the successful first
                # observation or be confused with an unreadable PDF render.
                quality["secondary_ocr_error"]={"error_type":type(error).__name__,"error":str(error)}
        score=lambda v:(sum(len(w["text"])*max(0,w["confidence"]-30) for w in v["words"]),v["weighted_confidence"] or 0)
        chosen=max(variants,key=score)
        quality.update(ocr_ink_metrics(pixels,chosen["words"]))
        return {"status":"ok","image_metrics":quality,"preview_sha256":sha(image),"ocr":chosen,
                "metrics_version":"ocr-ink-coverage-v1",
                "variants":[{k:v for k,v in variant.items() if k!="words"} for variant in variants],
                "confidence_interpretation":"Observed Tesseract word confidences; not VLM failure probabilities"}


def terminate_tree(process):
    if os.name=="nt":subprocess.run(["taskkill","/PID",str(process.pid),"/T","/F"],capture_output=True)
    else:
        try:os.killpg(process.pid,signal.SIGKILL)
        except ProcessLookupError:pass


def frame_payload(line):
    """Native PDF libraries may print diagnostics on stdout; ignore them."""
    position=line.rfind(WIRE_PREFIX)
    return line[position+len(WIRE_PREFIX):].strip() if position>=0 else None


def safe_worker(request):
    import pymupdf
    pymupdf.TOOLS.mupdf_display_errors(False)
    pymupdf.TOOLS.mupdf_display_warnings(False)
    pymupdf.TOOLS.mupdf_warnings(reset=True)
    try:result=worker(request)
    except Exception as error:
        result={"status":"error","error_phase":"render_or_quality","error_type":type(error).__name__,"error":str(error)}
    warnings=pymupdf.TOOLS.mupdf_warnings(reset=True)
    if warnings:result["render_warnings"]=warnings[-3000:]
    return result


def bounded_probe(page,config,temp_root,timeout):
    request=Path(temp_root)/(page["id"]+"_"+uuid.uuid4().hex+".json")
    request.write_text(canonical({"page":page,"config":config,"temp_root":str(temp_root)}),encoding="utf-8")
    options={"stdout":subprocess.PIPE,"stderr":subprocess.PIPE}
    if os.name=="nt":options["creationflags"]=subprocess.CREATE_NEW_PROCESS_GROUP|subprocess.CREATE_NO_WINDOW
    else:options["start_new_session"]=True
    started=time.monotonic()
    process=subprocess.Popen([sys.executable,"-X","utf8",str(Path(__file__).resolve()),"--worker",str(request)],**options)
    try:
        try:stdout,stderr=process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            terminate_tree(process);process.communicate()
            return {"status":"error","error":"OCR/render worker exceeded deadline","error_type":"timeout","seconds":round(time.monotonic()-started,3)}
        if process.returncode:
            return {"status":"error","error":stderr.decode("utf-8",errors="replace")[-2500:],"error_type":"worker_error","seconds":round(time.monotonic()-started,3)}
        payload=frame_payload(stdout.decode("utf-8"))
        if payload is None:
            return {"status":"error","error_phase":"worker_protocol","error_type":"MissingResultFrame",
                    "error":"OCR subprocess returned no framed result","seconds":round(time.monotonic()-started,3)}
        result=json.loads(payload);result["seconds"]=round(time.monotonic()-started,3)
        return result
    finally:request.unlink(missing_ok=True)


class StreamSession:
    """Persistent imports with one externally bounded request at a time."""
    def __init__(self,temp_root,timeout):
        self.temp_root=Path(temp_root);self.timeout=timeout;self.process=None;self.log=None

    def start(self):
        options={"stdin":subprocess.PIPE,"stdout":subprocess.PIPE,"text":True,"encoding":"utf-8","bufsize":1}
        if os.name=="nt":options["creationflags"]=subprocess.CREATE_NEW_PROCESS_GROUP|subprocess.CREATE_NO_WINDOW
        else:options["start_new_session"]=True
        self.log=(self.temp_root/("worker_"+uuid.uuid4().hex+".stderr.log")).open("ab")
        options["stderr"]=self.log
        self.process=subprocess.Popen([sys.executable,"-X","utf8",str(Path(__file__).resolve()),"--stream-worker"],**options)
        self.messages=queue.Queue();process=self.process;messages=self.messages
        def read():
            warnings=[]
            try:
                for line in process.stdout:
                    payload=frame_payload(line)
                    if payload is None:
                        warnings.append(line[:1000].strip());warnings=warnings[-10:]
                    else:
                        messages.put((payload,warnings));warnings=[]
            finally:messages.put(None)
        self.reader=threading.Thread(target=read,daemon=True);self.reader.start()

    def probe(self,page,config):
        if self.process is None or self.process.poll() is not None:self.start()
        started=time.monotonic()
        request={"page":page,"config":config,"temp_root":str(self.temp_root)}
        try:
            self.process.stdin.write(canonical(request)+"\n");self.process.stdin.flush()
            message=self.messages.get(timeout=self.timeout)
            if message is None:raise RuntimeError("Persistent OCR worker exited unexpectedly")
            payload,warnings=message
            result=json.loads(payload);result["seconds"]=round(time.monotonic()-started,3)
            if warnings:result["worker_stdout_messages"]=warnings
            return result
        except queue.Empty:
            terminate_tree(self.process);self.process.wait();self.log.close()
            return {"status":"error","error_type":"timeout","error":"OCR/render worker exceeded deadline",
                    "seconds":round(time.monotonic()-started,3)}
        except Exception as error:
            if self.process.poll() is None:terminate_tree(self.process);self.process.wait()
            self.log.close()
            return {"status":"error","error_type":type(error).__name__,"error":str(error),"seconds":round(time.monotonic()-started,3)}

    def close(self):
        if self.process is not None:
            if self.process.poll() is None:
                try:self.process.stdin.write("null\n");self.process.stdin.flush();self.process.wait(timeout=3)
                except Exception:terminate_tree(self.process);self.process.wait()
            if self.log and not self.log.closed:self.log.close()


class StreamPool:
    def __init__(self,temp_root,timeout):
        self.temp_root=temp_root;self.timeout=timeout;self.local=threading.local();self.sessions=[];self.lock=threading.Lock()
    def probe(self,page,config):
        if not hasattr(self.local,"session"):
            self.local.session=StreamSession(self.temp_root,self.timeout)
            with self.lock:self.sessions.append(self.local.session)
        return self.local.session.probe(page,config)
    def close(self):
        for session in self.sessions:session.close()


def append_journal(stream,value):
    compact=dict(value)
    if "ocr" in compact:compact["ocr"]={k:v for k,v in compact["ocr"].items() if k!="words"}
    stream.write(canonical(compact)+"\n");stream.flush()


def summarize_journal(out):
    """Small, current-version summaries without retaining text/word payloads."""
    latest={};invalid_lines=[]
    with (Path(out)/"ocr_journal.jsonl").open("rb") as stream:
        for number,line in enumerate(stream,1):
            if not line.endswith(b"\n"):break  # Producer may be mid-append.
            try:value=json.loads(line)
            except (ValueError,UnicodeDecodeError):invalid_lines.append(number);continue
            if value.get("config",{}).get("version")!=VERSION:continue
            ocr=value.get("ocr",{})
            latest[value["id"]]={"status":value["status"],"words":ocr.get("word_count"),
                                 "confidence":ocr.get("weighted_confidence"),"error_type":value.get("error_type"),
                                 "error_phase":value.get("error_phase")}
    records=list(latest.values());ocr=[r for r in records if r["status"]=="ok"]
    word_bin=lambda n:"0" if not n else "1-9" if n<10 else "10-49" if n<50 else "50+"
    confidence_bin=lambda c:"none" if c is None else "<40" if c<40 else "40-69" if c<70 else "70-84" if c<85 else "85+"
    result={"version":VERSION,"generated_unix":round(time.time()),"records":len(records),
            "status_counts":dict(Counter(r["status"] for r in records)),
            "word_count_bins":dict(Counter(word_bin(r["words"]) for r in ocr)),
            "confidence_bins":dict(Counter(confidence_bin(r["confidence"]) for r in ocr)),
            "error_types":dict(Counter(r["error_type"] for r in records if r["status"]=="error")),
            "error_phases":dict(Counter(r["error_phase"] or "legacy_unspecified" for r in records if r["status"]=="error")),
            "invalid_journal_lines":invalid_lines,"review_decisions_created":0}
    atomic_json(Path(out)/"ocr_partial_summary.json",result)
    return result


def ids_from_file(path):
    text=Path(path).read_text(encoding="utf-8-sig")
    try:
        value=json.loads(text)
        if isinstance(value,dict):value=value.get("ids",value.get("items",[]))
        return {item["id"] if isinstance(item,dict) else item for item in value}
    except json.JSONDecodeError:
        result=set()
        for line in text.split("\n"):
            if not line.strip():continue
            try:value=json.loads(line);result.add(value["id"] if isinstance(value,dict) else value)
            except json.JSONDecodeError:result.add(line.strip())
        return result


def evidence_identity(page,config):
    return hashlib.sha256(canonical({"page_identity":page["identity"],"config":config}).encode()).hexdigest()


def run(workspace,out,tessdata,workers=2,limit=None,ids_file=None,include_native=False,max_edge=1600,retry=True,timeout=90,persistent=True):
    workspace,out,tessdata=Path(workspace).resolve(),Path(out).resolve(),Path(tessdata).resolve()
    if not 1<=workers<=4:raise ValueError("Use1..4 bounded OCR workers")
    for language in ["vie","eng"]:
        if not (tessdata/(language+".traineddata")).is_file():raise ValueError("Missing OCR language "+language)
    config={"version":VERSION,"tesseract":str(DEFAULT_TESSERACT),"tessdata":str(tessdata),
            "model_sha256":{name:sha(tessdata/(name+".traineddata")) for name in ["vie","eng"]},
            "max_edge":max_edge,"ocr_timeout":35,"retry":retry,"include_native":include_native,
            "native_skip_min_chars":300,"languages":"vie+eng","psm_primary":3,"psm_retry":11}
    pages=read_jsonl(workspace/"pages.jsonl")
    if ids_file:
        wanted=ids_from_file(ids_file);pages=[p for p in pages if p["id"] in wanted]
        if len(pages)!=len(wanted):raise ValueError("Unknown requested OCR page IDs")
    if limit is not None:pages=pages[:limit]
    target=out/"ocr";target.mkdir(parents=True,exist_ok=True)
    temp_root=out/"ocr_work";temp_root.mkdir(exist_ok=True)
    history=out/"ocr_versions";history.mkdir(exist_ok=True)
    journal=(out/"ocr_journal.jsonl").open("a",encoding="utf-8",newline="\n")
    counters=Counter();results={};todo=[];started=time.monotonic()
    for page in pages:
        path=target/(page["id"]+".json");identity=evidence_identity(page,config)
        if path.exists():
            old=json.loads(path.read_text(encoding="utf-8"))
            # Failed/interrupted subprocesses are retryable observations, never
            # a permanent cache hit that could masquerade as unreadable content.
            if old.get("evidence_identity")==identity and old.get("status")!="error":
                results[page["id"]]={"status":old["status"]};counters["cached"]+=1;append_journal(journal,old);continue
        native_chars=len(re.sub(r"\s","",page.get("native_text_preview","")))
        skip=(not include_native and native_chars>=300
              and not set(page.get("reasons",[]))&{"unsupported_or_corrupt_glyph","repeated_character_corruption"})
        base={"id":page["id"],"page_identity":page["identity"],"source_id":page["source_id"],
              "source_sha256":page["source_sha256"],"page":page["page"],"bbox":page["bbox"],
              "native_char_count":native_chars,"evidence_identity":identity,"config":config}
        if skip:
            value={**base,"status":"native_skipped","reason":"native text has at least300 nonspace characters; native quality assessed separately"}
            atomic_json(path,value);results[page["id"]]={"status":value["status"]};counters["native_skipped"]+=1;append_journal(journal,value)
        else:todo.append((page,base))
    def publish_progress():
        atomic_json(out/"ocr_progress.json",{"total":len(pages),"complete":len(results),"queued_ocr":len(todo),
                    "counts":dict(counters),"seconds":round(time.monotonic()-started,2),"workers":workers})
    publish_progress()
    sessions=StreamPool(temp_root,timeout)
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures={executor.submit(sessions.probe,page,config) if persistent else executor.submit(bounded_probe,page,config,temp_root,timeout):(page,base) for page,base in todo}
        for future in as_completed(futures):
            # Release completed futures and their word arrays. Keeping all4k
            # OCR payloads in RAM would page heavily on the8GB review machine.
            page,base=futures.pop(future)
            try:value={**base,**future.result()}
            except Exception as error:value={**base,"status":"error","error_type":type(error).__name__,"error":str(error)}
            try:
                content_sha=hashlib.sha256((canonical(value)+"\n").encode("utf-8")).hexdigest()
                # The configuration identity remains inside the record. A
                # content digest alone also keeps Windows temp paths <MAX_PATH.
                version_path=history/page["id"]/(content_sha+".json")
                atomic_json(version_path,value);atomic_json(target/(page["id"]+".json"),value)
                results[page["id"]]={"status":value["status"]};counters[value["status"]]+=1
                append_journal(journal,value)
                publish_progress()
                if counters["ok"]%20==0 or value["status"]=="error":
                    print(canonical({"complete":len(results),"total":len(pages),"counts":dict(counters),"last":page["id"]}),flush=True)
            except Exception as error:
                # Log before executor shutdown. Its default wait would otherwise
                # keep running thousands of now-unpublishable queued probes.
                failure={"phase":"publish","page_id":page["id"],"error_type":type(error).__name__,
                         "error":str(error),"traceback":traceback.format_exc(),"complete":len(results)}
                try:atomic_json(out/("ocr_runtime_failure_"+uuid.uuid4().hex+".json"),failure)
                finally:
                    print(canonical(failure),file=sys.stderr,flush=True)
                    for pending in futures:pending.cancel()
                    sessions.close();journal.close()
                raise
    sessions.close();journal.close()
    with (out/"ocr_metrics.jsonl").open("w",encoding="utf-8",newline="\n") as stream:
        for page in pages:
            stream.write((target/(page["id"]+".json")).read_text(encoding="utf-8").strip()+"\n")
    report={"version":VERSION,"total":len(pages),"counts":dict(Counter(r["status"] for r in results.values())),
            "workers":workers,"seconds":round(time.monotonic()-started,2),"config":config,
            "review_decisions_created":0,"source_pdfs_modified":False,"vlm_inference_performed":False}
    atomic_json(out/"ocr_report.json",report);publish_progress();return report


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--worker",type=Path);parser.add_argument("--stream-worker",action="store_true")
    parser.add_argument("--workspace",type=Path);parser.add_argument("--out",type=Path);parser.add_argument("--tessdata",type=Path)
    parser.add_argument("--workers",type=int,default=2);parser.add_argument("--limit",type=int);parser.add_argument("--ids-file",type=Path)
    parser.add_argument("--include-native",action="store_true");parser.add_argument("--max-edge",type=int,default=1600)
    parser.add_argument("--no-retry",action="store_true");parser.add_argument("--timeout",type=float,default=90)
    parser.add_argument("--isolated-per-image",action="store_true")
    args=parser.parse_args()
    if args.stream_worker:
        for line in sys.stdin:
            request=json.loads(line)
            if request is None:break
            result=safe_worker(request)
            print(WIRE_PREFIX+canonical(result),flush=True)
            import pymupdf
            pymupdf.TOOLS.store_shrink(100)
    elif args.worker:
        print(WIRE_PREFIX+canonical(safe_worker(json.loads(args.worker.read_text(encoding="utf-8")))))
    else:
        if not all([args.workspace,args.out,args.tessdata]):parser.error("workspace,out,tessdata are required")
        print(canonical(run(args.workspace,args.out,args.tessdata,args.workers,args.limit,args.ids_file,args.include_native,args.max_edge,not args.no_retry,args.timeout,not args.isolated_per_image)))


if __name__=="__main__":main()
