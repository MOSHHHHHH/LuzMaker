#!/usr/bin/env node
"use strict";
const assert=require("node:assert/strict");
const fs=require("node:fs"),vm=require("node:vm");
const ctx=vm.createContext({Map,Set,Math,Array,Number,Error});
vm.runInContext(fs.readFileSync("packing.js","utf8"),ctx);
const pack=(sizes,cap)=>vm.runInContext("packPrintSections("+JSON.stringify(sizes.map((cost,index)=>({cost,index,part:1})))+","+cap+")",ctx);
function verify(sizes,cap){
 const pages=pack(sizes,cap);
 assert(pages.every(page=>page.used<=cap),"No page may exceed print capacity");
 assert.equal(pages.reduce((n,p)=>n+p.sections.length,0),sizes.length,"No section lost");
 const indices=pages.flatMap(p=>p.sections.map(s=>s.index)).sort((a,b)=>a-b);
 assert.deepEqual(indices,Array.from({length:sizes.length},(_,i)=>i),"Every section printed exactly once");
 return pages.length;
}
assert.equal(verify([6,5,3,2,2,2],10),2,"Exact search beats best-fit decreasing");
assert.equal(verify([4,4,2,2,2,2,2,2],10),2);
assert.equal(verify([7,7,7],10),3);
assert.equal(verify([9],10),1);
assert.equal(verify([],10),0);
assert.equal(verify(Array(20).fill(1),10),2,"Larger input uses bounded fallback");
assert.throws(()=>pack([11],10),/too large/);
console.log("PASS: bounded optimal print packing and lossless fallback");
