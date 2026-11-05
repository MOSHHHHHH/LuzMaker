#!/usr/bin/env node
"use strict";
const fs=require("node:fs"),vm=require("node:vm"),assert=require("node:assert/strict");
const html=fs.readFileSync("index.html","utf8");
const script=html.match(/<script>([\s\S]*?)<\/script>/)?.[1];
assert(script,"Inline app script missing");
const els=new Map();
function el(id){
 if(!els.has(id))els.set(id,{
  id,value:"",innerHTML:"",textContent:"",disabled:false,style:{},dataset:{},
  classList:{add(){},remove(){},toggle(){}},
  setAttribute(){},addEventListener(){},scrollIntoView(){},showModal(){},close(){},
  getAttribute(){return null}
 });
 return els.get(id);
}
const routes={
 "15": {routes:[{id:"base-15",name:"מסלול רגיל",stops:[{id:"S15",name:"תחנה רגילה"}],t:{"S15":[[1,510]]}}]},
 "15א": {routes:[{id:"letter-15",name:"מסלול חלופי",stops:[{id:"S15A",name:"תחנה חלופית"}],t:{"S15A":[[1,520]]}}]},
 "א15": {routes:[{id:"prefix-15",name:"מסלול נוסף",stops:[{id:"SX",name:"תחנה נוספת"}],t:{"SX":[[1,530]]}}]}
};
const idx={format:2,start:"2026-11-05",days:14,updated:"2026-11-05T07:00:00+02:00",lines:[
 ["15","15.json"],["15א","15a.json"],["א15","a15.json"]
]};
const data={"15.json":routes["15"],"15a.json":routes["15א"],"a15.json":routes["א15"]};
const doc={
 getElementById:el,
 querySelectorAll:()=>[],
 querySelector:()=>({onclick:null}),
 createElement:()=>({click(){},set href(v){},set download(v){}}),
};
const localStorage={getItem:()=>null,setItem(){}};
const sandbox={
 console,document:doc,window:{addEventListener(){},print(){}},
 localStorage,crypto:{randomUUID:()=>"test-id"},navigator:{},URL:{createObjectURL(){return "blob:fake"},revokeObjectURL(){}},
 Blob,Date,Map,Set,Array,JSON,Number,String,Math,Promise,Intl,structuredClone,
 alert(m){throw new Error("Unexpected alert: "+m)},confirm:()=>true,setTimeout,clearTimeout,
 fetch:async url=>{
  let value=url.endsWith("/data/index.json")?idx:data[url.split("/").at(-1)];
  return {ok:Boolean(value),json:async()=>value};
 }
};
vm.createContext(sandbox);
vm.runInContext(script,sandbox,{filename:"index.html"});
async function run(code){return vm.runInContext(code,sandbox)}
async function main(){
 await new Promise(resolve=>setTimeout(resolve,15));
 assert.equal((await run('catalog.lines.length')),3,"Catalog loaded");
 // Input with suffix must be distinct from the base line and prefix form.
 assert.equal((await run('lineMatches("15א")'))[0],"15א");
 assert.equal((await run('lineMatches("א15")'))[0],"א15");
 assert.equal((await run('lineMatches("15")'))[0],"15");
 await run("editGroup(null)");
 el("groupName").value="קו חלופי";
 el("lineNumber").value="15א";
 await run("chooseLine()");
 assert.equal(el("routeSelect").value,"0","Single route auto-selected");
 assert.equal(el("stopSelect").value,"S15A","Single stop auto-selected");
 // Regression: pressing Save immediately, without clicking Add, must add line.
 await run("saveGroup()");
 assert.equal((await run("groups.length")),1);
 assert.equal((await run("groups[0].lines.length")),1);
 assert.equal((await run("groups[0].lines[0].number")),"15א");
 assert.equal((await run("groups[0].lines[0].routeId")),"letter-15");
 assert.equal((await run("selectedGroup.id")),"test-id");
 // Automatic timetable search starts upon entering the generator.
 assert(!html.includes('id="manualMode"'),"Manual mode was removed");
 assert(!html.includes('id="analyze"'),"Explicit analyze button was removed");
 assert(html.includes('href="./favicon.svg"'),"Favicon linked");
 for(let i=0;i<50 && (await run('analyzed.length'))===0;i++)await new Promise(resolve=>setTimeout(resolve,10));
 assert.equal((await run('analyzed.length')),2,"Timetables must be detected automatically and grouped by identical schedules");
 assert.equal((await run('analyzed[0].dates.length')),1,"One date has the mocked departure");
 assert.equal((await run('analyzed[1].dates.length')),13,"Identical remaining dates are grouped");
 // Line legend uses real line numbers; duplicates start with (ב), never (א).
 const legend=await run('makeLineLegend([{number:"134",routeId:"r1",stopId:"s1",routeName:"מסלול 1",stopName:"תחנה 1"},{number:"134",routeId:"r2",stopId:"s2",routeName:"מסלול 2",stopName:"תחנה 2"},{number:"134",routeId:"r3",stopId:"s3",routeName:"מסלול 3",stopName:"תחנה 3"},{number:"134א",routeId:"ra",stopId:"sa",routeName:"מסלול אות",stopName:"תחנה אות"}])');
 assert.deepEqual([...legend.values()].map(x=>x.label),["134","134 (ב)","134 (ג)","134א"],"Labels should distinguish duplicates without confusing actual lettered lines");
 assert.equal(await run('labeledLine({line:"134",routeId:"r2",stopId:"s2"},makeLineLegend([{number:"134",routeId:"r1",stopId:"s1"},{number:"134",routeId:"r2",stopId:"s2"}]))'),"134 (ב)");
 assert(html.includes('id="resultLegend"'),"Printable legend exists");
 assert(html.includes('id="homeResults"'),"Home button exists");
 assert(html.includes('id="downloadActions"'),"Downloads are above the result tables");
 assert(html.indexOf('id="downloadActions"')<html.indexOf('id="resultTables"'),"Downloads appear first");
 assert(html.includes('["תאריך עברי","תאריך לועזי","קו","מסלול","תחנה","שעה"]'),"CSV exports both calendar dates and stop name");
 assert.equal(await run('hebrewDate("2026-11-05")'),"כ״ה בחשוון תשפ״ז","Hebrew calendar date for standard year");
 assert.equal(await run('hebrewDate("2024-03-24")'),"י״ד באדר ב׳ תשפ״ד","Leap-year Adar II");
 assert.equal(await run('hebrewDate("2024-02-24")'),"ט״ו באדר א׳ תשפ״ד","Leap-year Adar I");
 assert.equal(await run('gregorianDate("2024-03-24")'),"24.03.2024","Civil date preserved");
 assert((await run('dateDisplay("2024-03-24")')).includes("2024"),"Dual date view by default");
 await run('updateCalendarView("hebrew")');
 assert.equal(await run('dateDisplay("2024-03-24")'),"י״ד באדר ב׳ תשפ״ד","Hebrew-only calendar mode");
 await run('updateCalendarView("gregorian")');
 assert.equal(await run('dateDisplay("2024-03-24")'),"24.03.2024","Gregorian-only calendar mode");
 await run('updateCalendarView("both")');
 assert(!html.includes('<th style="width:70%">מסלול</th>'),"Timetable no longer repeats route name column");
 // Ensure route timings use the date mask and are not mixed with adjacent numbers.
 const day=await run('scheduleFor("2026-11-05")');
 assert.equal(day.length,1);
 assert.equal(day[0].line,"15א");
 assert.equal(day[0].min,520);
 console.log("PASS: 15, 15א and א15 distinct; selected line saved automatically; timetable produced");
}
main().catch(e=>{console.error(e);process.exitCode=1});
