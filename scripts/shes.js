/* SHES/SHES-T experimental implementation — specification v1.0, 2026-11-06.
 * Designed for locally generated, planned departure minutes only.
 * No rounding of scheduled departures, no removal of long gaps.
 */
const SHES=(()=>{
 const cost=(n,e)=>n>0?-2*(n*Math.log(n/e)-n):0;
 const finiteTimes=input=>input.filter(Number.isFinite).slice().sort((a,b)=>a-b);
 function periodsFor(t,delta=15,minMinutes=90,maxPeriods=6){
  const start=t[0],end=t[t.length-1],base=Math.floor(start/delta)*delta;
  const bins=Array(Math.floor((end-base)/delta)+1).fill(0);
  for(const x of t)bins[Math.floor((x-base)/delta)]++;
  const B=bins.length, minBins=Math.ceil(minMinutes/delta);
  if(B<minBins*2)return [{from:base,to:base+B*delta,count:t.length}];
  const prefix=[0];for(const x of bins)prefix.push(prefix.at(-1)+x);
  const seg=(i,j)=>({count:prefix[j]-prefix[i],exposure:(j-i)*delta});
  const dp=Array.from({length:maxPeriods+1},()=>Array(B+1).fill(Infinity));
  const back=Array.from({length:maxPeriods+1},()=>Array(B+1).fill(-1));
  dp[0][0]=0;
  for(let k=1;k<=maxPeriods;k++){
   for(let j=k*minBins;j<=B;j++){
    for(let i=(k-1)*minBins;i<=j-minBins;i++){
     if(!Number.isFinite(dp[k-1][i]))continue;
     const s=seg(i,j);
     // Do not invent a high-confidence segment from fewer than four trips.
     if(k>1&&s.count<4)continue;
     const candidate=dp[k-1][i]+cost(s.count,s.exposure);
     if(candidate<dp[k][j]){dp[k][j]=candidate;back[k][j]=i}
    }
   }
  }
  let best=Infinity,bestK=1;
  for(let k=1;k<=maxPeriods;k++){
   if(!Number.isFinite(dp[k][B]))continue;
   const criterion=dp[k][B]+(2*k-1)*Math.log(B);
   if(criterion<best){best=criterion;bestK=k}
  }
  const periods=[];let j=B;
  for(let k=bestK;k>=1;k--){
   const i=back[k][j];
   if(i<0)return [{from:base,to:base+B*delta,count:t.length}];
   periods.unshift({from:base+i*delta,to:base+j*delta,count:prefix[j]-prefix[i]});
   j=i;
  }
  // If the first region is sparse, the conservative choice is one period.
  if(periods.length>1&&periods.some(p=>p.count<4))
   return [{from:base,to:base+B*delta,count:t.length}];
  return periods;
 }
 function calculate(input,options={}){
  const t=finiteTimes(input);
  if(t.length<3)return {status:"insufficient",departures:t.length};
  const gaps=t.slice(1).map((x,i)=>x-t[i]),H=t.at(-1)-t[0];
  if(H<=0)return {status:"zero_span",departures:t.length};
  const periods=periodsFor(t,options.delta||15,options.minMinutes||90,options.maxPeriods||6);
  const groups=periods.map(()=>[]);
  const crossings=[];
  for(let i=0;i<gaps.length;i++){
   const midpoint=(t[i]+t[i+1])/2;
   const idx=Math.max(0,periods.findIndex(p=>midpoint>=p.from&&midpoint<p.to));
   groups[idx].push(gaps[i]);
   if(periods.some(p=>p.to>t[i]&&p.to<t[i+1]))crossings.push({from:t[i],to:t[i+1],minutes:gaps[i]});
  }
  const A=gaps.reduce((s,h)=>s+h*h,0);
  if(!A)return {status:"zero_span",departures:t.length};
  let R=0,toleranceSum=0,toleranceNorm=0;
  const described=periods.map((p,i)=>{
   const g=groups[i],q=g.length,span=g.reduce((s,v)=>s+v,0),mu=q?span/q:0;
   if(q){R+=span*span/q;const delta=Math.min(5,0.1*mu);
    toleranceSum+=g.reduce((s,h)=>s+Math.max(0,Math.abs(h-mu)-delta)**2,0);
    toleranceNorm+=q*mu*mu;
   }
   return {...p,gaps:q,meanHeadway:q?mu:null,frequencyPerHour:p.count*60/(p.to-p.from)};
  });
  const shes=100*R/A,shesT=toleranceNorm?100/(1+toleranceSum/toleranceNorm):null;
  return {status:"ok",departures:t.length,periods:described,SHES:shes,SHES_T:shesT,
   meanHeadway:H/gaps.length,maxHeadway:Math.max(...gaps),
   randomArrivalWait:A/(2*H),crossings,
   confidence:t.length<5?"very_low":t.length<8?"low":"normal"};
 }
 function analyze(times){
  const result=calculate(times);
  if(result.status!=="ok")return result;
  // Sensitivity grid from section D4: 10/15/20 bins, 60/90/120 min, 4/6/8 segments.
  // Memoization inside an analysis avoids repeated calculation for equivalent inputs.
  const comparisons=[];
  for(const delta of [10,15,20])for(const minMinutes of [60,90,120])
   for(const maxPeriods of [4,6,8]){
    const x=calculate(times,{delta,minMinutes,maxPeriods});
    if(x.status==="ok")comparisons.push(x.SHES_T);
   }
  const range=Math.max(...comparisons)-Math.min(...comparisons);
  result.sensitivity={min:Math.min(...comparisons),max:Math.max(...comparisons),range,
   unstable:range>5};
  return result;
 }
 return {calculate,analyze,periodsFor};
})();
