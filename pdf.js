/* Direct vector PDF export. Local fonts, measured A4 layout, Unicode BiDi. */
(function(root,factory){const api=factory(root);if(typeof module==='object'&&module.exports)module.exports=api;else root.LuzPDF=api})(typeof globalThis!=='undefined'?globalThis:this,function(root){
'use strict';
let ready;
function script(url){return new Promise((resolve,reject)=>{const s=document.createElement('script');s.src=url;s.onload=resolve;s.onerror=()=>{s.remove();reject(Error('לא ניתן לטעון את רכיבי ה־PDF. נסו שוב.'))};document.head.append(s)})}
function base64(bytes){let value='';for(let i=0;i<bytes.length;i+=8192)value+=String.fromCharCode(...bytes.subarray(i,i+8192));return btoa(value)}
async function dependencies(){
 if(!ready)ready=(async()=>{
  await Promise.all([root.jspdf?null:script('./assets/pdf/jspdf.umd.min.js'),root.bidi_js?null:script('./assets/pdf/bidi.min.js')]);
  const fonts=await Promise.all(['Regular','Bold'].map(async style=>{const response=await fetch('./assets/pdf/LuzSans-'+style+'.ttf');if(!response.ok)throw Error('לא ניתן לטעון את הגופן העברי ל־PDF.');return base64(new Uint8Array(await response.arrayBuffer()))}));
  let logo=null;
  try{const image=new Image();image.src='./logo.svg';await image.decode();const canvas=document.createElement('canvas');canvas.width=canvas.height=96;canvas.getContext('2d').drawImage(image,0,0,96,96);logo=canvas.toDataURL('image/png')}catch{}
  return {jsPDF:root.jspdf.jsPDF,bidiFactory:root.bidi_js,fonts,logo,pack:root.packPrintSections};
 })().catch(error=>{ready=null;throw error});
 return ready;
}
async function create(model,injected){
 const deps=injected||await dependencies();
 const doc=new deps.jsPDF({unit:'pt',format:'a4',orientation:'portrait',putOnlyUsedFonts:true,compress:true});
 for(const [i,style] of ['normal','bold'].entries()){const name='Luz-'+style+'.ttf';doc.addFileToVFS(name,deps.fonts[i]);doc.addFont(name,'Luz',style)}
 doc.setFont('Luz');doc.setLanguage('he-IL');doc.setProperties({title:model.title,author:'לו״ז מייקר',subject:'לוחות זמנים מתוכננים — משרד התחבורה',creator:'LuzMaker JavaScript PDF'});
 const bidi=deps.bidiFactory(),visualCache=new Map(),unsupported=new Set();
 const W=doc.internal.pageSize.getWidth(),H=doc.internal.pageSize.getHeight(),M=28.35,CW=W-2*M;
 const FONT=9,ROW=14,HEADER=15,GAP=10,FOOTER=28;
 function visual(value,dir='rtl'){
  const key=doc.getFont().fontStyle+'|'+dir+'|'+value;if(visualCache.has(key))return visualCache.get(key);
  const clean=Array.from(String(value),char=>{const cp=char.codePointAt(0);if(/\s|[\u200b-\u200f\u202a-\u202e\u2066-\u2069]/.test(char)||cp<=65535&&doc.getFont().metadata.characterToGlyph(cp))return char;unsupported.add(char);return '□'}).join('');
  const shaped=doc.processArabic(clean),levels=bidi.getEmbeddingLevels(shaped,dir);
  const v=bidi.getReorderedString(shaped,levels).replace(/[\u200e\u200f\u202a-\u202e\u2066-\u2069]/g,'');
  visualCache.set(key,v);return v;
 }
 function font(size,bold=false){doc.setFont('Luz',bold?'bold':'normal');doc.setFontSize(size)}
 function measure(value,size,bold=false){font(size,bold);return doc.getTextWidth(visual(value))}
 function wrap(value,width,size,bold=false){
  const lines=[];let line='';
  const words=String(value).replace(/\s+/g,' ').trim().split(' ');
  for(const word of words){
   if(measure(word,size,bold)>width){
    if(line){lines.push(line);line=''}
    const chars=root.Intl?.Segmenter?[...new Intl.Segmenter('he',{granularity:'grapheme'}).segment(word)].map(x=>x.segment):Array.from(word);
    for(const char of chars){if(line&&measure(line+char,size,bold)>width){lines.push(line);line=''}line+=char}
   }else if(line&&measure(line+' '+word,size,bold)>width){lines.push(line);line=word}else line+=(line?' ':'')+word;
  }
  if(line||!lines.length)lines.push(line);return lines;
 }
 function text(value,x,y,size=FONT,bold=false,align='right',dir='rtl',color='#172b4b'){
  font(size,bold);doc.setTextColor(color);doc.text(visual(value,dir),x,y,{align,isInputVisual:true,isInputRtl:false,isOutputVisual:true,isOutputRtl:false,isSymmetricSwapping:false});
 }
 function lines(values,x,y,size=FONT,bold=false,leading=12){for(const value of values){text(value,x,y,size,bold);y+=leading}return y}
 function badge(item,x,y,width,height=15){
  const colors=item.colors||['#153e73','#e7f0ff'];doc.setDrawColor(colors[0]);doc.setFillColor(colors[1]);doc.setLineWidth(.6);doc.roundedRect(x,y,width,height,3,3,'FD');
  const size=9;const value=String(item.label);if(measure(value,size,true)>width-5)throw Error('מספר קו ארוך מכדי להציג בגופן קריא. בחרו קבוצה מצומצמת יותר.');text(value,x+width/2,y+height/2+3,size,true,'center','rtl',colors[0]);
 }
 const titleLines=wrap(model.title,CW-(deps.logo?22:0),15,true),titleH=titleLines.length*19+10;
 const entries=model.legend||[],colW=(CW-10)/2,badgeW=48,detailW=colW-badgeW-21;
 const legendRows=[];
 for(let i=0;i<entries.length;i+=2){
  const row=entries.slice(i,i+2).map(item=>{
   const details=[...wrap(item.route,detailW,8.5,true).map(value=>({value,bold:true})),...wrap(item.agency||'',detailW,8.5).filter(Boolean).map(value=>({value})),...wrap('תחנה: '+item.stop,detailW,8.5).map(value=>({value}))];
   return {item,details,height:Math.max(25,details.length*11+10)};
  });legendRows.push({entries:row,height:Math.max(...row.map(x=>x.height))});
 }
 const legendH=18+legendRows.reduce((sum,row)=>sum+row.height+4,0)+8;
 const top=M+titleH+legendH,bottom=H-M-FOOTER,capacity=Math.floor(bottom-top);
 if(capacity<75)throw Error('המקרא ארוך מדי לעמוד A4 בגופן קריא. פצלו את הקבוצה או קצרו את שמות המסלולים.');
 const heads=(item,part,total)=>wrap(item.title+(total>1?' (חלק '+part+' מתוך '+total+')':''),CW,10,true);
 const full=[],tails=[];
 for(let index=0;index<model.timetables.length;index++){
  const item=model.timetables[index],rows=item.rows.slice().sort((a,b)=>a.min-b.min||String(a.label).localeCompare(String(b.label),'he'));
  let total=1,max=0,headerLines;
  for(let pass=0;pass<8;pass++){
   headerLines=heads(item,total,total);max=4*Math.floor((capacity-headerLines.length*13-HEADER-GAP-5)/ROW);
   if(max<4)throw Error('כותרת הלוח ארוכה מדי לעמוד. קצרו את שם הלוח.');
   const next=Math.max(1,Math.ceil(rows.length/max));if(next===total)break;total=next;
  }
  for(let part=1;part<=total;part++){
   const chunk=rows.slice((part-1)*max,part*max),head=heads(item,part,total);
   const cost=Math.ceil(head.length*13+5+(chunk.length?HEADER+Math.ceil(chunk.length/4)*ROW:20)+GAP);
   const section={index,part,total,rows:chunk,head,cost};
   if(cost>capacity)throw Error('לא ניתן לפרוס את הלוח בעמוד. קצרו את הכותרת.');
   if(part<total)full.push({used:cost,sections:[section]});else tails.push(section);
  }
 }
 const pack=deps.pack||root.packPrintSections;if(typeof pack!=='function')throw Error('מנוע פריסת העמודים אינו זמין.');
 // Full chunks cannot share a page with another block. Place them first, then
 // pack the sole tail of each timetable; no continuation can precede part 1.
 const pages=full.concat(pack(tails,capacity));
 function common(page){
  let y=M+15;
  if(deps.logo)doc.addImage(deps.logo,'PNG',W-M-15,M,15,15);
  lines(titleLines,W-M-(deps.logo?22:0),y,15,true,19);y=M+titleH;
  text('מקרא קווים ותחנות',W-M,y+10,10,true);y+=18;
  for(const row of legendRows){
   row.entries.forEach((entry,i)=>{const x=W-M-colW-i*(colW+10);doc.setDrawColor('#d4deeb');doc.setFillColor('#f8faff');doc.roundedRect(x,y,colW,row.height,3,3,'FD');badge(entry.item,x+colW-badgeW-5,y+5,badgeW);let dy=y+12;for(const detail of entry.details){text(detail.value,x+colW-badgeW-12,dy,8.5,detail.bold);dy+=11}});y+=row.height+4;
  }
  text(model.source||'מידע מתוכנן ממשרד התחבורה · יום תחבורתי \u206603:00–02:59\u2069 למחרת',W-M,H-M-10,8);
  text('עמוד '+(page+1)+' מתוך '+pages.length,M,H-M-10,8,false,'left');
 }
 pages.forEach((page,pageIndex)=>{
  if(pageIndex)doc.addPage('a4','portrait');common(pageIndex);let y=top;
  for(const section of page.sections.sort((a,b)=>a.index-b.index||a.part-b.part)){
   y=lines(section.head,W-M,y+10,10,true,13)-5;
   if(!section.rows.length){text('אין נסיעות ביום זה בתחנות שנבחרו',W-M,y+10);y+=20+GAP;continue}
   const count=Math.ceil(section.rows.length/4),columnW=(CW-3*9)/4;
   for(let column=0;column<4;column++){
    const rows=section.rows.slice(column*count,(column+1)*count);if(!rows.length)continue;
    const x=W-M-columnW-column*(columnW+9),right=x+columnW;
    doc.setFillColor('#eaf1fc');doc.rect(x,y,columnW,HEADER,'F');text('קו',right-5,y+10,9,true);text('שעה',x+26,y+10,9,true,'center');
    rows.forEach((row,i)=>{const yy=y+HEADER+i*ROW;doc.setDrawColor('#dce5f0');doc.setLineWidth(.25);doc.line(x,yy+ROW,right,yy+ROW);const item=entries.find(item=>item.key===row.key)||{label:row.label};badge({...item,label:row.label},right-48,yy+1,46,12);text(row.time,x+26,yy+10,FONT,false,'center','ltr')});
   }
   y+=HEADER+count*ROW+GAP;
   if(y>bottom+.1)throw Error('פריסת העמוד חורגת מגבולות ההדפסה.');
  }
 });
 doc.luzUnsupportedCharacters=[...unsupported];
 return doc;
}
return {create};
});
