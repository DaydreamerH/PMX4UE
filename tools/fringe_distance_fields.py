"""Convert geometry-derived angular fringe masks to clean contour distance fields.

CLI PNG I/O needs Pillow. Core chamfer math uses only the standard library.
This does not bake geometry, calibrate receivers, or change the face SDF.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path


def signed_field(mask, radius=16):
    """Positive inside; .5 boundary; truncated 8-neighbour chamfer approximation."""
    if isinstance(radius, bool) or not isinstance(radius, (int, float)) or not math.isfinite(radius) or radius <= 0:
        raise ValueError('radius must be finite and positive')
    height = len(mask)
    width = len(mask[0]) if height else 0
    if not width or any(len(row) != width for row in mask):
        raise ValueError('Nonempty rectangular mask required')
    if any(not isinstance(x, (int,float)) or not math.isfinite(x) or not 0 <= x <= 1
           for row in mask for x in row):
        raise ValueError('Mask samples must be finite in [0,1]')
    inside = [[x > .5 for x in row] for row in mask]

    def distance(region):
        d = [[radius if x == region else 0. for x in row] for row in inside]
        for reverse in (False, True):
            ys = range(height-1,-1,-1) if reverse else range(height)
            xs = range(width-1,-1,-1) if reverse else range(width)
            offsets = ((1,0),(0,1),(-1,1),(1,1)) if reverse else ((-1,0),(0,-1),(-1,-1),(1,-1))
            for y in ys:
                for x in xs:
                    for dx,dy in offsets:
                        xx,yy = x+dx,y+dy
                        if 0 <= xx < width and 0 <= yy < height:
                            d[y][x] = min(d[y][x],d[yy][xx]+(math.sqrt(2) if dx and dy else 1))
        return d

    a,b = distance(True),distance(False)
    return [[max(0,min(1,.5+(a[y][x]-b[y][x])/(2*radius)))
             for x in range(width)] for y in range(height)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--angles-a', required=True, type=Path)
    parser.add_argument('--angles-b', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--radius-pixels', type=float, default=16)
    args = parser.parse_args()
    from PIL import Image
    sources = [args.angles_a.resolve(),args.angles_b.resolve()]
    hashes = {str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    images = [Image.open(p).convert('RGBA') for p in sources]
    if images[0].size != images[1].size:
        raise ValueError('Angular masks must share dimensions and UV convention')
    if args.output.exists():
        raise ValueError('Use a fresh output directory; preserve earlier fields')
    w,h = images[0].size
    pixels = [list(im.getdata()) for im in images]
    if not any(p[3] for p in pixels[1]):
        raise ValueError('B.A must contain real receiver coverage')
    fields = []
    for src,channel in ((0,0),(0,1),(0,2),(0,3),(1,0)):
        mask = [[pixels[src][y*w+x][channel]/255 for x in range(w)] for y in range(h)]
        field = signed_field(mask,args.radius_pixels)
        fields.append([round(v*255) for row in field for v in row])
    args.output.mkdir(parents=True)
    outputs = []
    for name,data in (
        ('fringe_distance_A.png',list(zip(*fields[:4]))),
        ('fringe_distance_B.png',[(fields[4][i],0,0,pixels[1][i][3]) for i in range(w*h)])):
        dest = args.output/name
        image = Image.new('RGBA',(w,h))
        image.putdata(data)
        image.save(dest)
        outputs.append(dict(path=str(dest.resolve()),sha256=hashlib.sha256(dest.read_bytes()).hexdigest()))
    unchanged = all(hashlib.sha256(p.read_bytes()).hexdigest()==hashes[str(p)] for p in sources)
    report = dict(schema='pmx4ue.fringe-distance.v1',status='generated_visual_pending',
        input_hashes=hashes,source_unchanged=unchanged,resolution=[w,h],outputs=outputs,
        encoding='0.5 + signed chamfer pixel distance / (2*radius); positive inside',
        radius_pixels=args.radius_pixels,angles=[-90,-45,0,45,90],
        channels=dict(A=['-90','-45','0','+45'],B=['+90','unused','unused','receiver coverage']),
        uv_flip=False,ue_sampling='linear masks, sRGB=false; A.alpha is DATA, not opacity',
        limitations=['geometry bake and receiver calibration required',
                     'fixed bake elevation/reference pose', 'not runtime or visual approval'])
    (args.output/'fringe_distance.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    if not unchanged:
        raise RuntimeError('Source changed during conversion')


if __name__ == '__main__':
    main()
