/* Actual vector-PDF regression, no browser print renderer or OS fonts. */
'use strict';
const fs=require('node:fs'),path=require('node:path'),os=require('node:os'),vm=require('node:vm'),cp=require('node:child_process'),assert=require('node:assert/strict');
const {jsPDF}=require('../assets/pdf/jspdf.umd.min.js'),bidiFactory=require('../assets/pdf/bidi.min.js'),api=require('../pdf.js');
const sandbox={};vm.runInNewContext(fs.readFileSync('packing.js','utf8'),sandbox);
const deps={jsPDF,bidiFactory,fonts:['Regular','Bold'].map(s=>fs.readFileSync('assets/pdf/LuzSans-'+s+'.ttf').toString('base64')),pack:sandbox.packPrintSections};
const dir=process.env.LZM_PDF_ARTIFACTS_DIR||fs.mkdtempSync(path.join(os.tmpdir(),'lzm-vector-pdf-'));fs.mkdirSync(dir,{recursive:true});
const entry={key:'480',label:'480 (א)',route:'ביתר עילית ← תל אביב (ABC)',agency:'אגד',stop:'תחנה מרכזית / רחוב 123',colors:['#153e73','#e7f0ff']};
const make=(n,title,start=360)=>({title,rows:Array.from({length:n},(_,i)=>{const m=start+i*5;return {key:'480',label:entry.label,min:m,time:String(Math.floor(m/60)%24).padStart(2,'0')+':'+String(m%60).padStart(2,'0')}})});
(async()=>{
 try{
  const fixtures=[{name:'compact',tables:[make(12,'אמצע שבוע — י״ג בחשוון תשפ״ז'),make(14,'שישי — 13.11.2026'),make(5,'מוצאי שבת')],pages:1},{name:'long',tables:[make(205,'אמצע שבוע — י״ג בחשוון תשפ״ז')],pages:2},{name:'continuations',tables:[make(205,'לוח ראשון'),make(197,'לוח שני'),make(8,'לוח קצר',1500)]},{name:'mixed',tables:[make(4,'קו 15א (A4) — י״ג בחשוון תשפ״ז — 13.11.2026')],pages:1},{name:'empty',tables:[make(0,'ללא שירות')],pages:1}];
  const manifest=[];
  for(const f of fixtures){const d=await api.create({title:'לו״ז מייקר — קווים מביתר לתל אביב',legend:[entry],timetables:f.tables},deps);if(f.pages)assert.equal(d.getNumberOfPages(),f.pages,f.name);assert.deepEqual(d.luzUnsupportedCharacters,[]);const target=path.join(dir,f.name+'.pdf');fs.writeFileSync(target,Buffer.from(d.output('arraybuffer')));manifest.push({...f,file:target,rows:f.tables.flatMap(t=>t.rows).map(r=>r.time)});console.log('PASS: JS PDF',f.name,d.getNumberOfPages(),'pages')}
  const warning=await api.create({title:'אוטובוס 🚍',legend:[entry],timetables:[make(1,'לוח') ]},deps);assert.deepEqual(warning.luzUnsupportedCharacters,['🚍'],'Unsupported pictograms produce a visible replacement and explicit notice');
  fs.writeFileSync(path.join(dir,'manifest.json'),JSON.stringify(manifest));
  cp.execFileSync('python',['tests/check_generated_pdf.py',path.join(dir,'manifest.json')],{stdio:'inherit'});
 }finally{if(!process.env.LZM_PDF_ARTIFACTS_DIR)fs.rmSync(dir,{recursive:true,force:true})}
})().catch(e=>{console.error(e);process.exitCode=1});
