#!/usr/bin/env python3
"""Build page-only Canvas Common Cartridges from explicit, versioned course maps.
Based on the supplied HEALTHED 445 build_canvas_package.py; uses Python 3.9+ stdlib.
This tool does not contact authenticated Canvas or modify course settings.
"""
import argparse, concurrent.futures, csv, hashlib, html, json, re, sys
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit, unquote
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from zipfile import ZipFile, ZIP_DEFLATED, ZipInfo
import xml.etree.ElementTree as ET
CC='http://www.imsglobal.org/xsd/imsccv1p1/imscp_v1p1'
CV='http://canvas.instructure.com/xsd/cccv1p0'
ET.register_namespace('',CC)
VOID=set('area base br col embed hr img input link meta param source track wbr'.split())
def stable(value):return 'g'+hashlib.sha256(value.encode()).hexdigest()[:32]
def element(parent,name,value=None,namespace=CC,**attrs):
 e=ET.SubElement(parent,'{'+namespace+'}'+name,attrs)
 if value is not None:e.text=str(value)
 return e
def xml(root):return ET.tostring(root,encoding='utf-8',xml_declaration=True)
def allitems(cmap):return [x for m in cmap['modules'] for x in m['items']]
class Scan(HTMLParser):
 def __init__(self):
  super().__init__(convert_charrefs=True);self.links=[];self.issues=[];self.headings=[];self.stack=[];self.text=[];self.ids=[]
 def handle_starttag(self,tag,attrs):
  a=dict(attrs)
  if tag not in VOID:self.stack.append(tag)
  if a.get('id'):self.ids.append(a['id'])
  for k in ['href','src','poster']:
   if a.get(k):self.links.append((tag,k,a[k]))
  if tag in ['script','style']:self.issues.append(('error','Canvas-unsafe '+tag))
  if any(k.startswith('on') for k in a):self.issues.append(('error','Inline JavaScript event'))
  if tag=='img' and ('alt' not in a or a.get('data-review-alt')):self.issues.append(('review','Image needs meaningful alt review'))
  if tag=='iframe' and not a.get('title'):self.issues.append(('review','Iframe title missing'))
  if tag=='video' or tag=='audio':self.issues.append(('review','Verify captions/transcript'))
  if tag in ['h1','h2','h3','h4','h5','h6']:self.headings.append(int(tag[1]))
  if tag=='table':self.issues.append(('review','Verify table headers and mobile reflow'))
 def handle_startendtag(self,tag,attrs):
  self.handle_starttag(tag,attrs)
  if tag not in VOID:self.stack.pop()
 def handle_endtag(self,tag):
  if tag in VOID:return
  if not self.stack or self.stack[-1]!=tag:self.issues.append(('error','Unbalanced closing tag '+tag))
  if tag in self.stack:
   while self.stack:
    old=self.stack.pop()
    if old==tag:break
 def handle_data(self,data):self.text.append(data)
def validate(root):
 root=Path(root).resolve();cmap=json.loads((root/'course-map.json').read_text());items=allitems(cmap);issues=[];external={};native=[]
 ids=[x['id'] for x in items];titles=[x['title'] for x in items]
 for kind,values in [('id',ids),('title',titles)]:
  for value,n in Counter(values).items():
   if n>1:issues.append({'severity':'error','file':'course-map.json','finding':'Duplicate '+kind+': '+value})
 for x in items:
  path=(root/x['file']).resolve()
  if not path.is_relative_to(root):raise ValueError('Path escapes project')
  if not path.is_file():issues.append({'severity':'error','file':x['file'],'finding':'Missing page'});continue
  source=path.read_text();scan=Scan();scan.feed(source)
  for severity,finding in scan.issues:issues.append({'severity':severity,'file':x['file'],'finding':finding})
  if scan.stack:issues.append({'severity':'error','file':x['file'],'finding':'Unclosed HTML elements: '+','.join(scan.stack)})
  if len(scan.ids)!=len(set(scan.ids)):issues.append({'severity':'error','file':x['file'],'finding':'Duplicate HTML IDs'})
  if any(b>a+1 for a,b in zip(scan.headings,scan.headings[1:])):issues.append({'severity':'review','file':x['file'],'finding':'Heading level skip'})
  for marker in sorted(set(re.findall(r'\[(?:INSERT|INSTRUCTOR)[^\]]*\]|\{[^{}<>\n]{1,120}\}',source,re.I))):issues.append({'severity':'review','file':x['file'],'finding':'Unresolved field: '+html.unescape(marker)[:180]})
  if re.search(r'captioned.*(?:when available|being prepared)|need (?:video|lecture|rubric)|insert (?:lecture|video)',source,re.I):issues.append({'severity':'review','file':x['file'],'finding':'Media or assessment preparation remains'})
  for tag,attr,url in scan.links:
   parts=urlsplit(url)
   if parts.scheme in ['javascript','data']:issues.append({'severity':'error','file':x['file'],'finding':'Unsafe URL scheme'});continue
   if parts.scheme in ['mailto','tel']:continue
   if parts.scheme in ['http','https']:
    external.setdefault(url,[]).append(x['file'])
    if 'instructure.com' in parts.netloc and '/courses/' in parts.path:native.append({'file':x['file'],'url':url,'status':'Requires target-course rebind or verified existing native item'})
    continue
   if url.startswith('#'):
    if parts.fragment not in scan.ids:issues.append({'severity':'review','file':x['file'],'finding':'Review fragment '+url})
    continue
   target=(path.parent/unquote(parts.path)).resolve()
   if not target.is_relative_to(root) or not target.exists():issues.append({'severity':'error','file':x['file'],'finding':'Broken local link: '+url})
   elif attr=='href' and target.suffix=='.html' and target not in {(root/i['file']).resolve() for i in items}:issues.append({'severity':'review','file':x['file'],'finding':'Linked HTML is outside selected import pages: '+url})
 summary={'course':cmap['course'],'modules':len(cmap['modules']),'pages':len(items),'errors':sum(i['severity']=='error' for i in issues),'review_findings':sum(i['severity']=='review' for i in issues),'issues':issues,'external_links':[{'url':u,'pages':list(dict.fromkeys(p)),'status':'not checked'} for u,p in external.items()],'native_links':native,'import_verified':False}
 (root/'reports').mkdir(exist_ok=True);(root/'reports/validation.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False))
 return cmap,summary
def build(root):
 root=Path(root).resolve();cmap,report=validate(root)
 if report['errors']:raise ValueError(str(report['errors'])+' validation errors; see reports/validation.json')
 manifest=ET.Element('{'+CC+'}manifest',identifier=stable(cmap['course']))
 meta=element(manifest,'metadata');element(meta,'schema','IMS Common Cartridge');element(meta,'schemaversion','1.1.0')
 orgs=element(manifest,'organizations');org=element(orgs,'organization',identifier='org_1',structure='rooted-hierarchy');top=element(org,'item',identifier='LearningModules');element(top,'title',cmap['course'])
 resources=element(manifest,'resources');cvmods=ET.Element('{'+CV+'}modules');files={};mapping={}
 for item in allitems(cmap):mapping[(root/item['file']).resolve()]='wiki_content/'+stable(cmap['course']+':page:'+item['id'])+'.html'
 for mp,module in enumerate(cmap['modules'],1):
  mid=stable(cmap['course']+':module:'+module['id']);orgmod=element(top,'item',identifier=mid);element(orgmod,'title',module['title']);cvmod=element(cvmods,'module',namespace=CV,identifier=mid)
  for k,v in [('title',module['title']),('workflow_state','unpublished'),('position',mp),('require_sequential_progress','false'),('locked','false')]:element(cvmod,k,v,namespace=CV)
  cvitems=element(cvmod,'items',namespace=CV)
  for ip,item in enumerate(module['items'],1):
   pid=stable(cmap['course']+':page:'+item['id']);iid=stable(cmap['course']+':item:'+item['id']);path=(root/item['file']).resolve();href=mapping[path]
   res=element(resources,'resource',identifier=pid,type='webcontent',href=href);element(res,'file',href=href)
   oi=element(orgmod,'item',identifier=iid,identifierref=pid);element(oi,'title',item['title'])
   ci=element(cvitems,'item',namespace=CV,identifier=iid)
   for k,v in [('content_type','WikiPage'),('workflow_state','unpublished'),('title',item['title']),('identifierref',pid),('position',ip),('indent',0)]:element(ci,k,v,namespace=CV)
   element(ci,'new_tab',namespace=CV)
   body=path.read_text()
   # Rewrite only local href/src targets. Absolute native Canvas and external hosts remain explicit review items.
   def rewrite(m):
    attr,quote,url=m.group(1),m.group(2),html.unescape(m.group(3));parts=urlsplit(url)
    if parts.scheme or not parts.path or url.startswith('//'):return m.group(0)
    target=(path.parent/unquote(parts.path)).resolve()
    if target in mapping:
     result='$IMS-CC-FILEBASE$/'+mapping[target]
    elif target.is_relative_to(root) and target.is_file():
     rel='assets/'+target.relative_to(root).as_posix();files[rel]=target.read_bytes();element(res,'file',href=rel);result='$IMS-CC-FILEBASE$/'+rel
    else:return m.group(0)
    if parts.fragment:result+='#'+parts.fragment
    return attr+'='+quote+html.escape(result,quote=True)+quote
   body=re.sub(r'(href|src)\s*=\s*([\"\'])(.*?)\2',rewrite,body,flags=re.I)
   head=f'<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{html.escape(item["title"])}</title><meta name="identifier" content="{pid}"><meta name="editing_roles" content="teachers"><meta name="workflow_state" content="unpublished"></head><body>'
   files[href]=(head+body+'</body></html>').encode()
 files['course_settings/module_meta.xml']=xml(cvmods);files['course_settings/canvas_export.txt']=b'Canvas export package\n'
 # Omit course_settings.xml: importing page content must not replace destination course details.
 associated=element(resources,'resource',identifier=stable(cmap['course']+':settings'),type='associatedcontent/imscc_xmlv1p1/learning-application-resource',href='course_settings/canvas_export.txt')
 for name in ['course_settings/module_meta.xml','course_settings/canvas_export.txt']:element(associated,'file',href=name)
 files['imsmanifest.xml']=xml(manifest)
 dist=root/'dist';dist.mkdir(exist_ok=True);output=dist/(cmap['course'].replace(' ','-')+'-pages-review.imscc')
 with ZipFile(output,'w',ZIP_DEFLATED) as z:
  for name,data in sorted(files.items()):
   info=ZipInfo(name,(2026,11,20,0,0,0));info.compress_type=ZIP_DEFLATED;z.writestr(info,data)
 check_package(output,cmap)
 report['package']={'file':output.name,'sha256':hashlib.sha256(output.read_bytes()).hexdigest(),'zip_xml_references_verified':True,'canvas_import_verified':False}
 (root/'reports/validation.json').write_text(json.dumps(report,indent=2,ensure_ascii=False));return output,report
def check_package(path,cmap=None):
 with ZipFile(path) as z:
  assert z.testzip() is None,'Corrupt ZIP';names=set(z.namelist());manifest=ET.fromstring(z.read('imsmanifest.xml'));mods=ET.fromstring(z.read('course_settings/module_meta.xml'))
  refs={r.attrib['identifier'] for r in manifest.findall('.//{'+CC+'}resource')}
  for f in manifest.findall('.//{'+CC+'}file'):assert f.attrib['href'] in names,'Missing resource '+f.attrib['href']
  for i in manifest.findall('.//{'+CC+'}item'):
   if i.get('identifierref'):assert i.get('identifierref') in refs,'Dangling org resource'
  for i in mods.findall('.//{'+CV+'}item'):
   assert i.find('{'+CV+'}identifierref').text in refs,'Dangling Canvas module resource'
  for name in names:
   if name.endswith('.html'):
    s=z.read(name).decode()
    for ref in re.findall(r'\$IMS-CC-FILEBASE\$/([^\"\'<>#]+)',s):assert html.unescape(ref) in names,'Unpackaged local target '+ref
    assert 'name="workflow_state" content="unpublished"' in s,'Publication state missing'
  if cmap:
   observed=mods.findall('{'+CV+'}module');assert len(observed)==len(cmap['modules'])
   for actual,expected in zip(observed,cmap['modules']):
    assert actual.find('{'+CV+'}title').text==expected['title']
    assert [i.find('{'+CV+'}title').text for i in actual.findall('{'+CV+'}items/{'+CV+'}item')]==[i['title'] for i in expected['items']]
 return True
def external_check(root):
 root=Path(root).resolve();_,report=validate(root)
 def check(link):
  url=link['url'];parts=urlsplit(url)
  if any(v in parts.netloc for v in ['instructure.com','google.com','googleusercontent.com']) or parts.query and any(v in parts.query.lower() for v in ['token=','signature=','jwt=']):return dict(link,status='manual authenticated or deployment check')
  try:
   req=Request(url,headers={'User-Agent':'UWW-course-link-check/1.0'})
   with urlopen(req,timeout=15) as response:return dict(link,status='reachable',http_status=response.status,final_url=response.url)
  except HTTPError as e:return dict(link,status='http error; manual verification required',http_status=e.code)
  except Exception as e:return dict(link,status='unverified network failure',detail=str(e))
 results=list(concurrent.futures.ThreadPoolExecutor(max_workers=8).map(check,report['external_links']))
 (root/'reports/external-links.json').write_text(json.dumps(results,indent=2));return results
if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=['build','validate','check-package','check-external']);parser.add_argument('path',type=Path);args=parser.parse_args()
 try:
  if args.action=='build':
   output,report=build(args.path);print(json.dumps({'output':str(output),'modules':report['modules'],'pages':report['pages'],'errors':report['errors'],'review_findings':report['review_findings'],'canvas_import_verified':False}))
  elif args.action=='validate':
   _,report=validate(args.path);print(json.dumps({k:report[k] for k in ['course','modules','pages','errors','review_findings']}));sys.exit(bool(report['errors']))
  elif args.action=='check-package':print(check_package(args.path))
  else:print(json.dumps(Counter(i['status'] for i in external_check(args.path))))
 except Exception as e:print('ERROR:',e,file=sys.stderr);sys.exit(1)
