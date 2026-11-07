"use strict";
// Israeli civil-day event labels. These are descriptive labels, not claims of GTFS special service.
function specialDayName(iso){
 const date=new Date(iso+"T12:00:00Z");
 const p=new Intl.DateTimeFormat("en-u-ca-hebrew",{day:"numeric",month:"long",timeZone:"UTC"}).formatToParts(date);
 const day=Number(p.find(x=>x.type==="day")?.value);
 const month=String(p.find(x=>x.type==="month")?.value||"").toLowerCase().replace(/[^a-z0-9]/g,"");
 const is=(...names)=>names.includes(month);
 if(is("tishri","tishrei")){
  if(day===1||day===2)return "ראש השנה";
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
 if(is("kislev")&&day>=25||is("tevet")&&day<=2)return "חנוכה";
 if(is("tevet")&&day===10)return "עשרה בטבת";
 if(is("shevat","shvat")&&day===15)return "ט״ו בשבט";
 if(is("adar","adarii","adar2")&&day===14)return "פורים";
 if(is("adar","adarii","adar2")&&day===15)return "שושן פורים";
 if(is("iyar","iyyar")&&day===18)return "ל״ג בעומר";
 if(is("sivan")&&day===5)return "ערב שבועות";
 if(is("sivan")&&day===6)return "שבועות";
 if(is("av")&&day===9)return "תשעה באב";
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
