#!/usr/bin/env node
"use strict";
const fs=require("node:fs"),vm=require("node:vm"),assert=require("node:assert/strict");
const scope=vm.createContext({Date,Intl,Set,Map,Number,String,Array});
vm.runInContext(fs.readFileSync("aliases.js","utf8"),scope);
const run=expr=>vm.runInContext(expr,scope);
assert.equal(run('specialDayName("2024-04-22")'),"ערב פסח");
assert.equal(run('specialDayName("2024-04-23")'),"פסח");
assert.equal(run('specialDayName("2024-04-24")'),"חול המועד פסח");
assert.equal(run('specialDayName("2024-10-03")'),"ראש השנה");
assert.equal(run('specialDayName("2024-10-12")'),"יום כיפור");
assert.equal(run('specialDayName("2024-03-24")'),"פורים");
assert.equal(run('specialDayName("2024-03-25")'),"שושן פורים");
assert.equal(run('specialDayName("2024-11-05")'),null);
const unique=run('uniqueAliases([{alias:"חג"},{alias:"חג"},{alias:"חג (1)"},{alias:"חג"}]).map(x=>x.alias)');
assert.deepEqual([...unique],["חג","חג (1)","חג (1) (1)","חג (2)"]);
assert.equal(run('normalizeAlias("  יום   שישי ")'),"יום שישי");

// Shifted Israeli observances must use their OBSERVED civil dates.
assert.equal(run('specialDayName("2024-05-06")'),"יום השואה");
assert.equal(run('specialDayName("2024-05-13")'),"יום הזיכרון");
assert.equal(run('specialDayName("2024-05-14")'),"יום העצמאות");
assert.equal(run('specialDayName("2025-04-24")'),"יום השואה");
assert.equal(run('specialDayName("2025-04-30")'),"יום הזיכרון");
assert.equal(run('specialDayName("2025-05-01")'),"יום העצמאות");
assert.equal(run('specialDayName("2026-04-22")'),"יום העצמאות");
// Deferred fast: 9 Av 5785 was Saturday; the fast moved to Sunday, Aug 3.
assert.equal(run('specialDayName("2025-08-03")'),"תשעה באב");
assert.equal(run('specialDayName("2029-07-22")'),"תשעה באב");
// Each Kislev 25 must start exactly eight calendar days of Hanukkah.
for(const year of [2024,2025,2026,2027,2028,2029,2030]){
 let first=null;
 const formatter=new Intl.DateTimeFormat("en-u-ca-hebrew",{day:"numeric",month:"long",timeZone:"UTC"});
 for(let d=new Date(Date.UTC(year,10,1,12));d.getUTCFullYear()===year;d.setUTCDate(d.getUTCDate()+1)){
  const p=formatter.formatToParts(d);
  if(p.find(x=>x.type==="month")?.value==="Kislev"&&Number(p.find(x=>x.type==="day")?.value)===25){first=new Date(d);break}
 }
 assert(first,year+": no Kislev 25");
 for(let offset=0;offset<=8;offset++){
  const d=new Date(first);d.setUTCDate(d.getUTCDate()+offset);
  const val=run('specialDayName('+JSON.stringify(d.toISOString().slice(0,10))+')');
  assert.equal(val==="חנוכה",offset<8,year+": Hanukkah day "+(offset+1));
 }
}
run('setHolidaySnapshot({events:{"2026-11-09":["סיגד"],"2026-11-10":["מועד ניסיוני"]}})');
assert.equal(run('specialDayName("2026-11-09")'),"סיגד");
assert.equal(run('specialDayName("2026-11-10")'),"מועד ניסיוני","CI holiday snapshot takes precedence");
run('setHolidaySnapshot({events:{}})');
const protectedManual=run('uniqueAliases([{alias:"ערב פסח",manual:true},{alias:"ערב פסח"},{alias:"ערב פסח",manual:true}]).map(x=>x.alias)');
assert.deepEqual([...protectedManual],["ערב פסח","ערב פסח (1)","ערב פסח"],"Manual duplicate remains invalid rather than being silently renamed");
assert.equal(run('specialDayName("2026-09-11")'),"ערב ראש השנה");
assert.equal(run('suggestedHolidayAlias(["2026-09-10","2026-09-11"],"gregorian",x=>x,{})'),"אמצע שבוע (כולל ערב ראש השנה)","A weekday and a holiday with identical GTFS times share a descriptive title");
assert.equal(run('suggestedHolidayAlias(["2026-09-10","2026-09-11","2026-11-09"],"gregorian",x=>x,{})'),"אמצע שבוע (כולל ערב ראש השנה ו־סיגד)","Two different holidays are included by name");
assert.equal(run('suggestedHolidayAlias(["2026-09-11","2026-11-09"],"gregorian",x=>x,{})'),"מועדים מיוחדים (כולל ערב ראש השנה ו־סיגד)","Two holidays without regular days retain both names");
assert.equal(run('suggestedHolidayAlias(["2026-09-12","2026-09-13"],"hebrew",x=>x,{})'),"ראש השנה","Multiple dates of the same holiday retain the holiday title");
assert.equal(run('suggestedHolidayAlias(["2026-09-10","2026-09-11","2026-11-09"],"gregorian",x=>x,{})').length<=70,true,"Generated title respects the editor length cap");


assert.equal(run('specialDayName("2026-11-09")'),"סיגד");
assert.equal(run('specialDayName("2026-01-01")'),"ראש השנה האזרחית");
console.log("PASS: Hebrew events, civil-day labeling, deterministic collision suffixes");
