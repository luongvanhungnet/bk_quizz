"""Source transforms; geometry is proposed evidence, never semantic approval."""
import math
from PIL import Image

def union(boxes,pad=0):
    if not boxes:return [0,0,1000,1000]
    return [max(0,min(b[0] for b in boxes)-pad),max(0,min(b[1] for b in boxes)-pad),
            min(1000,max(b[2] for b in boxes)+pad),min(1000,max(b[3] for b in boxes)+pad)]
def local_box(b,clip):return [round(max(0,min(1000,(b[i]-clip[i%2])*1000/(clip[i%2+2]-clip[i%2]))),3) for i in range(4)]
def parent_box(b,clip):return [round(clip[i%2]+b[i]*(clip[i%2+2]-clip[i%2])/1000,3) for i in range(4)]
def crop(source,target,clip):
    im=Image.open(source).convert('RGB');w,h=im.size
    pixels=[max(0,int(math.floor(clip[0]*w/1000))),max(0,int(math.floor(clip[1]*h/1000))),
            min(w,int(math.ceil(clip[2]*w/1000))),min(h,int(math.ceil(clip[3]*h/1000)))]
    if pixels[2]<=pixels[0] or pixels[3]<=pixels[1]:raise ValueError('Empty task crop')
    effective=[pixels[0]*1000/w,pixels[1]*1000/h,pixels[2]*1000/w,pixels[3]*1000/h]
    im.crop(pixels).save(target);return effective
def fit_image(im,max_visual_tokens):
    """Use 28-pixel grid with a hard bound before processor resize."""
    budget=max_visual_tokens*28*28;w,h=im.size;area=max(1,w*h)
    minimum=min(64,max_visual_tokens)*28*28
    scale=math.sqrt(minimum/area) if area<minimum else min(1,math.sqrt(budget/area))
    grid=lambda v:(math.ceil(v/28-1e-9) if area<minimum else math.floor(v/28+1e-9))*28
    rw=max(28,grid(w*scale));rh=max(28,grid(h*scale))
    while rw*rh>budget:
        if rw>=rh and rw>28:rw-=28
        elif rh>28:rh-=28
        else:raise ValueError('Image budget too small')
    return im.convert('RGB').resize((rw,rh),Image.Resampling.LANCZOS)
def endpoint_consistent(edge,nodes,tolerance=100):
    a=nodes.get(edge['source']);b=nodes.get(edge['target'])
    if not a or not b:return False
    box=edge['bbox']
    def distance(n):
        x=(n['bbox'][0]+n['bbox'][2])/2;y=(n['bbox'][1]+n['bbox'][3])/2
        return math.hypot(max(box[0]-x,0,x-box[2]),max(box[1]-y,0,y-box[3]))
    return distance(a)<=tolerance and distance(b)<=tolerance
