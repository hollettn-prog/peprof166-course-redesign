"""Generate UTF-8 review documents without changing Canvas-ready HTML fragments."""
import html,json,re,sys
from pathlib import Path
root=Path(sys.argv[1]).resolve();mp=json.loads((root/'course-map.json').read_text())
for m in mp['modules']:
 for x in m['items']:
  rel=Path(x['file']).relative_to('canvas/pages');dest=root/'review/pages'/rel;dest.parent.mkdir(parents=True,exist_ok=True)
  dest.write_text('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+html.escape(x['title'])+'</title><style>body{margin:20px 12px}a{color:#4F2D7F}a:focus-visible{outline:3px solid #7654A3;outline-offset:3px}img,iframe,video{max-width:100%}@media(max-width:600px){body{margin:0 8px}}</style></head><body>'+ (root/x['file']).read_text()+'</body></html>')
p=root/'review/index.html';p.write_text(p.read_text().replace('../canvas/pages/','pages/'))
