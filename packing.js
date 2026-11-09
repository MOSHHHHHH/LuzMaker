"use strict";
/**
 * Pack measured/estimated print sections into A4 sheets.
 * Exact minimum sheet count for <=16 sections within a bounded search budget;
 * best-fit decreasing is retained as a safe fallback for larger/complex sets.
 * The fit model is expressed in print-row units, not CSS pixel measurements.
 */
function packPrintSections(sections, capacity) {
 if(!Number.isInteger(capacity)||capacity<=0)throw new Error("Invalid page capacity");
 const ordered=sections.map((section,i)=>({...section,_sequence:i})).sort(
  (a,b)=>b.cost-a.cost||a.index-b.index||a.part-b.part
 );
 if(ordered.some(x=>!Number.isInteger(x.cost)||x.cost<0||x.cost>capacity))
  throw new Error("A print section is too large for a single page");
 const bfd=[];
 for(const section of ordered) {
  let best=-1,smallest=Infinity;
  for(let i=0;i<bfd.length;i++) {
   const spare=capacity-bfd[i].used-section.cost;
   if(spare>=0&&spare<smallest){best=i;smallest=spare}
  }
  if(best===-1){bfd.push({used:0,sections:[]});best=bfd.length-1}
  bfd[best].used+=section.cost;
  bfd[best].sections.push(section);
 }
 const sum=ordered.reduce((v,s)=>v+s.cost,0);
 const lower=Math.ceil(sum/capacity);
 if(ordered.length>16||lower===bfd.length)return bfd;
 // A bounded branch-and-bound search; never block the browser indefinitely.
 let attempts=0;
 const LIMIT=160000;
 for(let count=lower;count<bfd.length;count++){
  const loads=Array(count).fill(0),sets=Array.from({length:count},()=>[]);
  let solution=null,exhausted=false;
  function place(i){
   if(++attempts>LIMIT){exhausted=true;return false}
   if(i===ordered.length) {
    solution=sets.filter(x=>x.length).map(x=>({
     used:x.reduce((n,s)=>n+s.cost,0),sections:x.slice()
    }));
    return true;
   }
   const item=ordered[i],seen=new Set();
   for(let b=0;b<count;b++){
    const load=loads[b];
    if(seen.has(load)||load+item.cost>capacity)continue;
    seen.add(load);
    loads[b]+=item.cost;sets[b].push(item);
    if(place(i+1))return true;
    sets[b].pop();loads[b]-=item.cost;
    if(exhausted||load===0)break;
   }
   return false;
  }
  if(place(0))return solution;
  if(exhausted)break;
 }
 return bfd;
}
