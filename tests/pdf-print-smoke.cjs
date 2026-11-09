#!/usr/bin/env node
"use strict";
const fs=require("node:fs"),os=require("node:os"),path=require("node:path"),vm=require("node:vm");
const cp=require("node:child_process"),assert=require("node:assert/strict");
const html=fs.readFileSync("index.html","utf8");
const css=html.match(/<style>([\s\S]*?)<\/style>/)?.[1];
const start=html.indexOf("function printTimetableSheets(timetables,legend){");
const end=html.indexOf("function createResults(readSelection=true){",start);
assert(css&&start>=0&&end>start,"Print renderer or styles missing");
const sandbox={
 timetableDates:x=>x.flatMap(y=>y.dates),selectedGroup:{name:"בדיקת לוחות"},
 safe:x=>String(x).replace(/&/g,"&amp;").replace(/</g,"&lt;"),
 dateListDisplay:x=>x.join(", "),
 lineBadge:x=>'<strong class="line-number color-line">'+x+"</strong>",
 labeledLine:x=>x.line,
 legendIdentity:x=>x.line+"\x1f"+x.routeId+"\x1f"+x.stopId,
 resultLegendHtml:legend=>'<h3>מקרא קווים ותחנות</h3><div class="legend-grid">'+[...legend.values()].map(x=>'<div class="legend-entry"><strong>'+x.label+"</strong><div>"+x.route+'<div class="muted">'+x.stop+"</div></div></div>").join("")+"</div>",
 timeString:m=>String(Math.floor(m/60)%24).padStart(2,"0")+":"+String(m%60).padStart(2,"0"),
 Math,Map,Set,Array,Number,String,Error
};
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync("packing.js","utf8")+"\n"+html.slice(start,end),sandbox);
const browser=["google-chrome","chromium","chromium-browser"].find(x=>{try{cp.execFileSync("which",[x],{stdio:"ignore"});return true}catch{return false}});
if(!browser){console.log("SKIP: no headless Chromium");process.exit(0)}
const dir=fs.mkdtempSync(path.join(os.tmpdir(),"lzm-pdf-"));
const legend=new Map([["480",{label:"480",route:"ירושלים - תל אביב",stop:"תחנה מרכזית"}]]);
const make=(count,name)=>({alias:name,dates:["2026-11-09"],rows:Array.from({length:count},(_,i)=>({line:"480",routeId:"r1",stopId:"s1",min:360+i*5}))});
try{
 fs.copyFileSync("logo.svg",path.join(dir,"logo.svg"));
 const fixtures=[{name:"compact",list:[make(12,"אמצע שבוע"),make(14,"שישי"),make(5,"מוצאי שבת")],expected:1},{name:"long",list:[make(205,"אמצע שבוע")],expected:2}];
 for(const f of fixtures){
  const sheets=sandbox.printTimetableSheets(f.list,legend);
  const page='<!doctype html><html lang="he" dir="rtl"><head><meta charset="utf-8"><style>'+css+'</style></head><body><div id="results"><h2 id="printTitle">לו״ז מייקר</h2><div id="resultLegend"></div><div id="resultTables"></div><div id="printTables">'+sheets+"</div></div></body></html>";
  const target=path.join(dir,f.name+".html"),pdf=path.join(dir,f.name+".pdf");
  fs.writeFileSync(target,page);
  cp.execFileSync(browser,["--headless","--no-sandbox","--disable-gpu","--disable-dev-shm-usage","--no-pdf-header-footer","--print-to-pdf="+pdf,"file://"+target],{timeout:30000,stdio:"pipe"});
  const binary=fs.readFileSync(pdf).toString("latin1");
  const pages=(binary.match(/\/Type\s*\/Page\b/g)||[]).length;
  assert.equal(pages,f.expected,f.name+": expected "+f.expected+" pages, got "+pages);
  console.log("PASS: Chrome PDF",f.name,pages,"page(s)");
 }
}finally{fs.rmSync(dir,{recursive:true,force:true})}
