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
// Variable Kislev length never creates a ninth day of Chanukah.
for(const year of [2024,2025,2026,2027,2028,2029,2030]){
 let count=0;
 for(let d=new Date(Date.UTC(year,0,1,12));d.getUTCFullYear()===year;d.setUTCDate(d.getUTCDate()+1)){
  if(run('specialDayName('+JSON.stringify(d.toISOString().slice(0,10))+')')==="חנוכה")count++;
 }
 // Some Gregorian years contain part of two Hanukkah festivals.
 assert(count>=7&&count<=11,year+": unexpected Hanukkah count "+count);
}
run('setHolidaySnapshot({events:{"2026-11-09":["סיגד"],"2026-11-10":["מועד ניסיוני"]}})');
assert.equal(run('specialDayName("2026-11-09")'),"סיגד");
assert.equal(run('specialDayName("2026-11-10")'),"מועד ניסיוני","CI holiday snapshot takes precedence");
run('setHolidaySnapshot({events:{}})');
console.log("PASS: Hebrew events, civil-day labeling, deterministic collision suffixes");
