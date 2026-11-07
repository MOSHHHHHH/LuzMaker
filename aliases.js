"use strict";
// Israeli civil-day event labels. These are descriptive labels, not claims of GTFS special service.
let holidaySnapshot=Object.create(null);
function setHolidaySnapshot(payload){
 holidaySnapshot=payload&&typeof payload==="object"&&payload.events&&typeof payload.events==="object"?payload.events:Object.create(null);
}
function specialDayName(iso){
 const official=holidaySnapshot[iso];
 if(Array.isArray(official)&&official.length)return official[0];
 const date=new Date(iso+"T12:00:00Z");
 const p=new Intl.DateTimeFormat("en-u-ca-hebrew",{day:"numeric",month:"long",timeZone:"UTC"}).formatToParts(date);
 const day=Number(p.find(x=>x.type==="day")?.value);
 const month=String(p.find(x=>x.type==="month")?.value||"").toLowerCase().replace(/[^a-z0-9]/g,"");
 const is=(...names)=>names.includes(month);
 const weekday=date.getUTCDay();
 // Modern observances follow Israel's legally shifted dates, not a fixed
 // Hebrew day number. The official Hebcal snapshot takes priority when present.
 function observedModern(nominalMonth,nominalDay,shiftFn){
  for(let delta=-6;delta<=6;delta++){
   const nominal=new Date(date);nominal.setUTCDate(nominal.getUTCDate()+delta);
   const p=new Intl.DateTimeFormat("en-u-ca-hebrew",{day:"numeric",month:"long",timeZone:"UTC"}).formatToParts(nominal);
   const m=String(p.find(x=>x.type==="month")?.value||"").toLowerCase().replace(/[^a-z0-9]/g,"");
   const d=Number(p.find(x=>x.type==="day")?.value);
   if(nominalMonth.includes(m)&&d===nominalDay){
    const dayOfWeek=nominal.getUTCDay();
    const observed=new Date(nominal);observed.setUTCDate(observed.getUTCDate()+shiftFn(dayOfWeek));
    return observed.toISOString().slice(0,10)===iso;
   }
  }
  return false;
 }
 const independenceShift=weekday=>weekday===5?-1:weekday===6?-2:weekday===1?1:0;
 if(observedModern(["iyar","iyyar"],5,independenceShift))return "יום העצמאות";
 if(observedModern(["iyar","iyyar"],5,weekday=>independenceShift(weekday)-1))return "יום הזיכרון";
 if(observedModern(["nisan","nissan"],27,weekday=>weekday===5?-1:weekday===0?1:0))return "יום השואה";
 const shifted=(delta,m,d)=>{const x=new Date(date);x.setUTCDate(x.getUTCDate()+delta);const pp=new Intl.DateTimeFormat("en-u-ca-hebrew",{day:"numeric",month:"long",timeZone:"UTC"}).formatToParts(x);return Number(pp.find(z=>z.type==="day")?.value)===d&&namesMonth(pp.find(z=>z.type==="month")?.value)===m};
 function namesMonth(v){return String(v||"").toLowerCase().replace(/[^a-z0-9]/g,"")}
 // Postponed minor fasts are observed on Sunday when their nominal day falls on Shabbat.
 if(weekday===0&&is("tishri","tishrei")&&day===4&&shifted(-1,month,3))return "צום גדליה";
 if(weekday===0&&is("av")&&day===10&&shifted(-1,"av",9))return "תשעה באב";
 if(weekday===0&&is("tammuz","tamuz")&&day===18&&shifted(-1,month,17))return "שבעה עשר בתמוז";
 if(is("tishri","tishrei")){
  if(day===1||day===2)return "ראש השנה";
  if(day===3&&weekday!==6)return "צום גדליה";
  if(day===9)return "ערב יום כיפור";
  if(day===10)return "יום כיפור";
  if(day===14)return "ערב סוכות";
  if(day===15)return "סוכות";
  if(day>=16&&day<=20)return "חול המועד סוכות";
  if(day===21)return "הושענא רבה";
  if(day===22)return "שמיני עצרת ושמחת תורה";
 }
 if(is("nisan","nissan")){
  if(day===14)return "ערב פסח";
  if(day===15)return "פסח";
  if(day>=16&&day<=20)return "חול המועד פסח";
  if(day===21)return "שביעי של פסח";
 }
 if(is("kislev")&&day>=25)return "חנוכה";
 if(is("tevet")&&day<=3){
  // The 8th day falls on 2 or 3 Tevet depending on Kislev\u2019s length.
  const before=new Date(date);before.setUTCDate(before.getUTCDate()-7);
  const previous=new Intl.DateTimeFormat("en-u-ca-hebrew",{day:"numeric",month:"long",timeZone:"UTC"}).formatToParts(before);
  const prevDay=Number(previous.find(x=>x.type==="day")?.value);
  if(day<=2||(day===3&&prevDay===25))return "חנוכה";
 }
 if(is("tevet")&&day===10)return "עשרה בטבת";
 if(is("shevat","shvat")&&day===15)return "ט״ו בשבט";
 if(is("adar","adarii","adar2")&&day===13&&weekday!==6)return "תענית אסתר";
 if(is("adar","adarii","adar2")&&day===11&&weekday===4){const next=new Date(date);next.setUTCDate(next.getUTCDate()+2);const parts=new Intl.DateTimeFormat("en-u-ca-hebrew",{day:"numeric",month:"long",timeZone:"UTC"}).formatToParts(next);if(Number(parts.find(x=>x.type==="day")?.value)===13)return "תענית אסתר"}
 if(is("adar","adarii","adar2")&&day===14)return "פורים";
 if(is("adar","adarii","adar2")&&day===15)return "שושן פורים";
 if(is("adari","adar1")&&day===14)return "פורים קטן";
 if(is("adar","adarii","adar2")&&day===13)return "ערב פורים";
 if(is("iyar","iyyar")&&day===14)return "פסח שני";
 if(is("iyar","iyyar")&&day===18)return "ל״ג בעומר";
 if(is("iyar","iyyar")&&day===28)return "יום ירושלים";
 if(is("sivan")&&day===5)return "ערב שבועות";
 if(is("sivan")&&day===6)return "שבועות";
 if(is("tammuz","tamuz")&&day===17&&weekday!==6)return "שבעה עשר בתמוז";
 if(is("av")&&day===8)return "ערב תשעה באב";
 if(is("av")&&day===9&&weekday!==6)return "תשעה באב";
 if(is("av")&&day===15)return "ט״ו באב";
 if(is("heshvan","cheshvan")&&day===29)return "סיגד";
 if(is("elul")&&day===29)return "ערב ראש השנה";
 return null;
}
function suggestedHolidayAlias(dates,calendarView,dateDisplay,visibility){
 const holidays=dates.map(specialDayName);
 if(holidays.length&&holidays.every(h=>h&&h===holidays[0]))return holidays[0];
 const w=dates.map(x=>new Date(x+"T12:00:00Z").getUTCDay());
 if(w.length&&w.every(d=>d<=4))return "אמצע שבוע";
 if(w.length&&w.every(d=>d===5))return "יום שישי";
 if(w.length&&w.every(d=>d===6))return "מוצ״ש";
 return dates.length?dateDisplay([...dates].sort()[0],calendarView,visibility):"לוח מיוחד";
}
function normalizeAlias(name){return String(name||"").trim().replace(/\s+/g," ").toLocaleLowerCase("he")}
function uniqueAliases(items){
 const used=new Set();
 return items.map(item=>{
  const base=String(item.alias||"").trim()||"לוח";
  let alias=base,n=1;
  while(used.has(normalizeAlias(alias)))alias=base+" ("+(n++)+")";
  used.add(normalizeAlias(alias));
  return {...item,alias};
 });
}
