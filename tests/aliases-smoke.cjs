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
console.log("PASS: Hebrew events, civil-day labeling, deterministic collision suffixes");
