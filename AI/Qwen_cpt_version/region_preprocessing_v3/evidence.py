"""Native PDF/vector and raster-board candidates; none are semantic ground truth."""
import hashlib
from pathlib import Path
import re
import math


def overlap(a,b):return max(0,min(a[2],b[2])-max(a[0],b[0]))*max(0,min(a[3],b[3])-max(a[1],b[1]))
def norm_box(b,clip):
    return [round(max(0,min(1000,(b[i]-clip[i%2])*1000/(clip[i%2+2]-clip[i%2]))),3) for i in range(4)]


def native_context(page,request):
    scale=page['render_width']/page['page_size_pt'][0];clip=request['bbox_pixels']
    lines=[];inside=[];anchors=[];crop_spans=[]
    for block in page['blocks']:
        for line in block.get('lines',[]):
            b=[v*scale for v in line['bbox']];area=max(1,(b[2]-b[0])*(b[3]-b[1]))
            if overlap(b,clip)>0:
                lines.append((b,line['text']))
                if overlap(b,clip)/area>=.95:inside.append(line['text'])
            for span in line.get('spans',[]):
                box=[v*scale for v in span['bbox']];text=span.get('text','').strip()
                if text and len(text)<=12 and overlap(box,clip)>0:
                    normalized=norm_box(box,clip)
                    if normalized[2]>normalized[0] and normalized[3]>normalized[1]:
                        anchors.append({'text':text,'bbox':normalized,'kind':'native_label_or_weight_candidate'})
                if text and overlap(box,clip)/max(1,(box[2]-box[0])*(box[3]-box[1]))>=.95:crop_spans.append(text)
    surrounding='\n'.join(text for b,text in lines)
    all_lines=[l for block in page['blocks'] for l in block.get('lines',[])]
    center=(clip[1]+clip[3])/2/scale
    nearest=sorted(all_lines,key=lambda l:abs((l['bbox'][1]+l['bbox'][3])/2-center))[:5]
    return {'native_text':'\n'.join(b['text'] for b in page['blocks']),
            'native_local_context':surrounding or '\n'.join(l['text'] for l in nearest),
            'native_crop_text':' '.join(crop_spans) if crop_spans else '\n'.join(inside),'native_anchors':anchors,
            'document_sha256':page['document_sha256'],'render_sha256':page['render_sha256']}


def vector_candidates(pdf_page,page,request):
    scale=page['render_width']/page['page_size_pt'][0];clip=request['bbox_pixels'];paths=[]
    for d in pdf_page.get_drawings():
        rect=[v*scale for v in d['rect']]
        # Stroked straight lines can have zero-area bounding boxes.
        padded=[rect[0]-1,rect[1]-1,rect[2]+1,rect[3]+1]
        if overlap(padded,clip)<=0:continue
        if (rect[2]-rect[0])*(rect[3]-rect[1])>page['render_width']**2*.9:continue
        lines=[]
        for item in d['items']:
            if item[0]=='l':
                a,b=item[1:3]
                coords=[(a.x*scale-clip[0])*1000/(clip[2]-clip[0]),(a.y*scale-clip[1])*1000/(clip[3]-clip[1]),
                        (b.x*scale-clip[0])*1000/(clip[2]-clip[0]),(b.y*scale-clip[1])*1000/(clip[3]-clip[1])]
                if all(0<=v<=1000 for v in coords):lines.append([round(v,3) for v in coords])
            elif item[0]=='re':
                rect=item[1];rw=rect.width;rh=rect.height
                if max(rw,rh)>5*max(.001,min(rw,rh)):
                    if rw>rh:a=(rect.x0,(rect.y0+rect.y1)/2);b=(rect.x1,(rect.y0+rect.y1)/2)
                    else:a=((rect.x0+rect.x1)/2,rect.y0);b=((rect.x0+rect.x1)/2,rect.y1)
                    coords=[(a[0]*scale-clip[0])*1000/(clip[2]-clip[0]),(a[1]*scale-clip[1])*1000/(clip[3]-clip[1]),
                            (b[0]*scale-clip[0])*1000/(clip[2]-clip[0]),(b[1]*scale-clip[1])*1000/(clip[3]-clip[1])]
                    if all(0<=v<=1000 for v in coords):lines.append([round(v,3) for v in coords])
        if not lines:continue
        paths.append({'bbox':norm_box(padded,clip),'segments':lines,'stroke_rgb':d.get('color'),
                      'fill_rgb':d.get('fill'),'width_pt':d.get('width'),
                      'possible_arrowhead':bool(d.get('fill') is not None and 2<=len(lines)<=4 and
                                               (rect[2]-rect[0])<35*scale and (rect[3]-rect[1])<35*scale),
                      'semantic_verified':False})
    return paths


def native_graph_candidates(pdf_page,page,request,context):
    """Anchor native straight paths to round node shapes; ambiguous labels stay null."""
    scale=page['render_width']/page['page_size_pt'][0];clip=request['bbox_pixels'];nodes=[];unresolved=[]
    for d in pdf_page.get_drawings():
        b=[v*scale for v in d['rect']];w=b[2]-b[0];h=b[3]-b[1]
        if min(w,h)<=3 or not .7<w/h<1.4 or sum(i[0]=='c' for i in d['items'])<3:continue
        if overlap(b,clip)/max(1,w*h)<.98:continue
        box=norm_box(b,clip)
        if not 8<max(box[2]-box[0],box[3]-box[1])<180:continue
        labels=[]
        for a in context['native_anchors']:
            x=(a['bbox'][0]+a['bbox'][2])/2;y=(a['bbox'][1]+a['bbox'][3])/2
            if box[0]<=x<=box[2] and box[1]<=y<=box[3] and re.fullmatch(r'[A-Za-z0-9]{1,3}',a['text']):labels.append(a['text'])
        unique=sorted(set(labels))
        proposal={'id':'v'+str(d['seqno']),'bbox':box,'label':unique[0] if len(unique)==1 else None,
                  'label_candidates':unique,'semantic_verified':False}
        if len(unique)!=1:
            unresolved.append({**proposal,'reason':'unlabelled_or_ambiguous_shape'});continue
        if box[0]<150 and box[1]>880:
            unresolved.append({**proposal,'reason':'margin_identifier_candidate_not_removed_from_source'});continue
        if any(overlap(box,n['bbox'])/max(1,(box[2]-box[0])*(box[3]-box[1]))>.95 for n in nodes):continue
        nodes.append(proposal)
    def nearest(x,y):
        ranked=[]
        for n in nodes:
            b=n['bbox'];cx=(b[0]+b[2])/2;cy=(b[1]+b[3])/2
            distance=math.hypot(x-cx,y-cy);radius=max(b[2]-b[0],b[3]-b[1])/2
            if distance<=radius+28:ranked.append((distance,n['id']))
        return min(ranked)[1] if ranked else None
    edges=[]
    for path in context.get('vector_paths',[]):
        if path['possible_arrowhead']:continue
        for x1,y1,x2,y2 in path['segments']:
            a=nearest(x1,y1);b=nearest(x2,y2)
            if not a or not b or a==b:continue
            candidate={'source':a,'target':b,'bbox':[max(0,min(x1,x2)-2),max(0,min(y1,y2)-2),min(1000,max(x1,x2)+2),min(1000,max(y1,y2)+2)],
                       'weight_candidates':[],'arrowhead_candidates':[],'stroke_rgb':path['stroke_rgb'],'semantic_verified':False}
            length=max(1,math.hypot(x2-x1,y2-y1))
            for anchor in context['native_anchors']:
                if not re.fullmatch(r'[-−]?\d+(?:\.\d+)?',anchor['text']):continue
                box=anchor['bbox'];cx=(box[0]+box[2])/2;cy=(box[1]+box[3])/2
                t=((cx-x1)*(x2-x1)+(cy-y1)*(y2-y1))/length**2
                distance=abs((x2-x1)*(y1-cy)-(x1-cx)*(y2-y1))/length
                if .12<t<.88 and distance<25:candidate['weight_candidates'].append(anchor)
            for arrow in context.get('vector_paths',[]):
                if not arrow['possible_arrowhead']:continue
                box=arrow['bbox'];cx=(box[0]+box[2])/2;cy=(box[1]+box[3])/2
                if min(math.hypot(cx-x1,cy-y1),math.hypot(cx-x2,cy-y2))<35:candidate['arrowhead_candidates'].append(box)
            aliases=[e for e in edges if {e['source'],e['target']}=={a,b} and max(abs(v-u) for v,u in zip(e['bbox'],candidate['bbox']))<15]
            if aliases:
                aliases[0]['coincident_path_aliases']=aliases[0].get('coincident_path_aliases',0)+1
            else:edges.append(candidate)
    return {'nodes':nodes,'edges':edges,'unresolved_shapes':unresolved,'basis':'native_geometry_candidates_not_verified',
            'limitations':'Only round nodes and straight paths; paths crossing nodes, curves and labels can be ambiguous.'}


def board_candidates(path,board_size=4):
    import cv2
    import numpy as np
    im=cv2.imread(str(path));h,w=im.shape[:2];hsv=cv2.cvtColor(im,cv2.COLOR_BGR2HSV)
    blue=cv2.inRange(hsv,(75,20,50),(125,255,255));orange=cv2.inRange(hsv,(3,90,100),(35,255,255))
    mask=cv2.bitwise_or(blue,orange);mask=cv2.morphologyEx(mask,cv2.MORPH_CLOSE,np.ones((3,3),np.uint8))
    count,labels,stats,centers=cv2.connectedComponentsWithStats(mask)
    out=[]
    for x,y,bw,bh,pixels in stats[1:]:
        if min(bw,bh)<18 or not .7<bw/max(1,bh)<1.4 or max(bw,bh)>max(w,h)*.4 or pixels/(bw*bh)<.4:continue
        queens=[];removed=[];ambiguous=[]
        for row in range(board_size):
            for col in range(board_size):
                x1=int(x+(col+.3)*bw/board_size);x2=int(x+(col+.7)*bw/board_size)
                y1=int(y+(row+.3)*bh/board_size);y2=int(y+(row+.7)*bh/board_size)
                oq=orange[y1:y2,x1:x2];bl=blue[y1:y2,x1:x2];values=hsv[y1:y2,x1:x2,2]
                if oq.size==0:ambiguous.append([row,col]);continue
                if np.mean(oq>0)>.45:queens.append([row,col])
                elif np.mean(bl>0)>.4 and float(np.median(values))<210:removed.append([row,col])
        out.append({'bbox':[round(x/w*1000,2),round(y/h*1000,2),round((x+bw)/w*1000,2),round((y+bh)/h*1000,2)],
                    'board_size':board_size,'queens':queens,'removed_cells':removed,'ambiguous_cells':ambiguous,
                    'basis':'HSV_geometry_proposal_not_verified','semantic_verified':False})
    return sorted(out,key=lambda b:(b['bbox'][1],b['bbox'][0]))
