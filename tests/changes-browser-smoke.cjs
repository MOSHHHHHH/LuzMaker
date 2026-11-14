'use strict';
const assert=require('node:assert/strict'),{spawn,execFileSync}=require('node:child_process'),fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {chromium}=require('playwright');
(async()=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'lzm-changes-'));
 execFileSync('python',['-m','tests.make_ui_fixture',root],{stdio:'pipe'});
 const server=spawn('python',['-m','http.server','8765','--bind','127.0.0.1','--directory',path.join(root,'site')],{stdio:'ignore'});let browser;
 try{
  browser=await chromium.launch({executablePath:process.env.CHROME_BIN||'/usr/bin/chromium',args:['--no-sandbox']});
  const page=await browser.newPage({viewport:{width:1200,height:900}});await page.clock.install({time:new Date('2026-11-13T12:00:00Z')});const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto('http://127.0.0.1:8765/changes.html');
  await page.locator('#station').fill('תחנה מרכזית ביתר');
  await page.waitForSelector('#stationSuggestions:not([hidden])');
  assert.equal(await page.locator('.suggestion').count(),2,'Same-name physical stations remain distinct');
  await page.locator('#station').press('ArrowUp');assert.equal(await page.locator('#station').getAttribute('aria-activedescendant'),'suggestion-1');await page.locator('#station').press('ArrowDown');await page.locator('#station').press('Enter');
  await page.waitForSelector('#results article');
  assert.equal(await page.locator('#stopCode').innerText(),'12345');
  assert.ok(await page.locator('#results article').count()<10,'Daily repetitions are grouped into useful change cards');assert.deepEqual(await page.locator('#results article').evaluateAll(cards=>cards.map(c=>c.dataset.priority)),['0','3'],'Route changes precede schedule changes across lines');assert.equal(await page.getByRole('button',{name:'המסלול המעודכן והתחנות שהשתנו',exact:true}).count(),0);
  assert.match(await page.locator('#results').innerText(),/ביתר עילית/);
  await page.locator('#station').fill('רחוקה');await page.waitForSelector('#stationSuggestions:not([hidden])');assert.equal(await page.locator('.suggestion').count(),1);await page.locator('#station').fill('x');await page.locator('#station').press('Enter');await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('לפחות שתי אותיות'));assert.equal(await page.locator('#stopCode').innerText(),'12345','A short new query must not select an old suggestion');await page.locator('#station').fill('12345');
  let releaseRequest,requestBegan;const held=new Promise(r=>releaseRequest=r),began=new Promise(r=>requestBegan=r);const hash=require('node:crypto').createHash('sha256').update('12345').digest('hex').slice(0,20);const delayed='**/changes/stations/'+hash+'.json';await page.route(delayed,async route=>{requestBegan();await held;await route.continue()});await page.locator('#station').fill('12345');await page.locator('#station').press('Enter');await began;await page.locator('#station').fill('רחוקה');releaseRequest();await page.waitForFunction(()=>!document.querySelector('#workspace').hidden);assert.equal(await page.evaluate(()=>document.activeElement.id),'station','A completed old search must not steal focus from a newly typed query');await page.unroute(delayed);await page.locator('#station').fill('12345');
  assert.equal(await page.evaluate(()=>{const base={station:'s',line:'line',type:'schedule_changed',before:{count:1},after:{count:2},beforeProfile:'A',afterProfile:'B'};return grouped([{...base,date:'2026-11-13'},{...base,date:'2026-11-14',beforeProfile:'B',afterProfile:'A'},{...base,date:'2026-11-15'}]).length}),3,'A return between identical changes is never merged away');
  assert.equal(await page.locator('[data-period="all"]').getAttribute('aria-selected'),'true','All is the default');await page.locator('#saveStation').click();await page.reload();assert.match(await page.locator('#savedStations').innerText(),/12345/);await page.locator('#savedStations button').first().click();await page.waitForSelector('#results article');
  await page.selectOption('#category','route_changed');await page.locator('.detail-button').first().click();await page.waitForSelector('.change-details[data-loaded="true"]');assert.match(await page.locator('.change-details').first().innerText(),/פרטי שינוי המסלול/);assert.equal(await page.locator('.departures-table').count(),0,'Route-only changes show route details only');assert.match(await page.locator('.change-details .removed').first().innerText(),/הוסרה/);assert.equal(await page.getByRole('dialog',{name:/מידע נוסף/}).isVisible(),true);assert.equal(await page.locator('#closeChangeDialog').evaluate(el=>el===document.activeElement),true);await page.keyboard.press('Escape');assert.equal(await page.locator('#changeDialog').isVisible(),false);assert.equal(await page.locator('.detail-button').first().evaluate(el=>el===document.activeElement),true,'Closing restores focus to the triggering change');
  await page.selectOption('#category','all');await page.locator('#nearby summary').click();
  assert.equal(await page.locator('#nearbyChoices input[value="12346"]').count(),1);assert.equal(await page.locator('#nearbyChoices input[value="12347"]').count(),0,'333m stop excluded during preprocessing');
  await page.locator('#nearbyChoices input[value="12346"]').check();await page.locator('#addNearby').click();
  await page.waitForSelector('.chip');assert.match(await page.locator('#selectedChips').innerText(),/12346/);
  await page.getByRole('button',{name:'הסר את תחנה 12346 מהתצוגה'}).click();assert.equal(await page.locator('.chip').count(),0);
  await page.locator('[data-period="past"]').click();assert.equal(await page.locator('#results article').count(),0);
  await page.locator('[data-period="all"]').click();
  await page.setViewportSize({width:375,height:812});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  if(process.env.LZM_SCREENSHOT_DIR)await page.screenshot({path:path.join(process.env.LZM_SCREENSHOT_DIR,'changes-mobile.png')});
  await page.locator('#station').fill('12348');await page.locator('#station').press('Enter');await page.waitForFunction(()=>document.querySelector('#stopCode').textContent==='12348'&&!document.querySelector('#workspace').hidden);assert.match(await page.locator('#results').innerText(),/לא נמצאו/);
  await page.locator('#station').fill('999999');await page.locator('#station').press('Enter');await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('לא נמצאה תחנה'));
  await page.route('**/changes/stations/*.json',async route=>{const response=await route.fetch();const data=await response.json();const event=data.changes.find(e=>e.before&&e.after);assert.ok(event);event.before.first=26375;event.after.first=26354;await route.fulfill({response,json:data})});
  await page.locator('#station').fill('12345');await page.locator('#station').press('Enter');await page.waitForSelector('#results article');await page.locator('[data-period="all"]').click();assert.match(await page.locator('#results').innerText(),/07:19:35/);assert.match(await page.locator('#results').innerText(),/07:19:14/);await page.unroute('**/changes/stations/*.json');
  await page.selectOption('#category','schedule_changed');await page.locator('.detail-button').first().click();await page.waitForSelector('.departures-table');assert.equal(await page.locator('.change-details .route-list').count(),0,'Schedule-only changes do not show route details');await page.locator('#closeChangeDialog').click();await page.selectOption('#category','all');

  // Service additions and removals also get the same information modal, and
  // structural changes outrank schedule-only cards even on the same line.
  await page.evaluate(()=>{
   window.originalSources=sources;const data=sources.get(primary),base=data.changes.find(e=>e.scheduleChanged&&!e.routeChanged);
   const added={...base,id:'test-added',date:'2026-11-11',comparisonDate:'2026-11-04',type:'added',before:{count:0,first:null,last:null,meanInterval:null},beforeProfile:null,beforeRoutes:[],tags:['נוסף שירות ביום זה']};
   const removed={...base,id:'test-removed',date:'2026-11-12',comparisonDate:'2026-11-05',type:'removed',after:{count:0,first:null,last:null,meanInterval:null},afterProfile:null,routes:[],tags:['לא יפעל שירות ביום זה']};
   sources=new Map([[primary,{...data,changes:[...data.changes,added,removed]}]]);render();
  });
  const priorities=await page.locator('#results article').evaluateAll(cards=>cards.map(c=>c.dataset.priority));assert.deepEqual(priorities.slice(0,3),['0','1','2']);assert.ok(priorities.slice(3).length>0&&priorities.slice(3).every(p=>p==='3'),'All schedule-only cards follow structural changes');
  for(const type of ['added','removed']){await page.locator('article[data-change-type="'+type+'"] .detail-button').click();await page.waitForSelector('#changeDialogBody[data-loaded="true"]');assert.match(await page.locator('#changeDialogBody').innerText(),/פרטי לוח הזמנים/);assert.match(await page.locator('#changeDialogBody').innerText(),type==='added'?/מסלול השירות החדש/:/מסלול השירות שבוטל בתחנה/);await page.locator('#closeChangeDialog').click()}
  await page.evaluate(()=>{sources=window.originalSources;delete window.originalSources;render();detailsCache.clear()});
  // A failed lazy load can be retried within the modal.
  await page.route('**/changes/details/*.json',r=>r.fulfill({status:503,body:'temporary'}));
  await page.locator('.detail-button').first().click();await page.getByRole('button',{name:'נסה שוב',exact:true}).waitFor();
  await page.unroute('**/changes/details/*.json');await page.getByRole('button',{name:'נסה שוב',exact:true}).click();await page.waitForSelector('#changeDialogBody[data-loaded="true"]');
  await page.setViewportSize({width:375,height:812});assert.ok(await page.locator('#changeDialog').evaluate(el=>el.scrollWidth<=el.clientWidth),'Modal fits mobile viewport');
  if(process.env.LZM_SCREENSHOT_DIR)await page.screenshot({path:path.join(process.env.LZM_SCREENSHOT_DIR,'changes-modal.png')});
  await page.keyboard.press('Escape');

  // Closing while details are loading must not repopulate or reopen the modal.
  await page.evaluate(()=>detailsCache.clear());let releaseDetails,detailsStarted;
  const detailsHeld=new Promise(r=>releaseDetails=r),detailsBeginning=new Promise(r=>detailsStarted=r);
  await page.route('**/changes/details/*.json',async route=>{detailsStarted();await detailsHeld;await route.continue()});
  await page.locator('.detail-button').first().click();await detailsBeginning;await page.keyboard.press('Escape');releaseDetails();
  await page.evaluate(async()=>{await loadDetails(primary);await Promise.resolve()});
  assert.equal(await page.locator('#changeDialog').isVisible(),false);assert.equal(await page.locator('#changeDialogBody').innerText(),'');
  await page.unroute('**/changes/details/*.json');
  await page.route('**/data/stations/*.json',r=>r.fulfill({status:503,body:'temporary'}));
  await page.locator('#station').fill('12345');await page.locator('#station').press('Enter');await page.waitForFunction(()=>document.querySelector('#stationDescription').textContent.includes('פרטי התחנה אינם זמינים'));assert.ok(await page.locator('#results article').count()>0);await page.unroute('**/data/stations/*.json');
  await page.route('**/changes/stations/*.json',r=>r.fulfill({status:500,body:'error'}));
  await page.locator('#station').fill('12345');await page.locator('#station').press('Enter');await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('נסו שוב'));
  const night=await browser.newPage();await night.clock.install({time:new Date('2026-11-13T00:30:00Z')});await night.goto('http://127.0.0.1:8765/changes.html');await night.locator('#station').fill('12345');await night.locator('#station').press('Enter');await night.waitForSelector('#results article');assert.equal(await night.evaluate(()=>transportToday()),'2026-11-12','02:30 is the preceding transport day');await night.clock.setFixedTime(new Date('2026-11-13T01:05:00Z'));await night.locator('[data-period="current"]').click();assert.ok((await night.locator('#results article h4').allTextContents()).length>0);assert.equal(await night.evaluate(()=>transportToday()),'2026-11-13','An already-open page follows the03:00 transport-day rollover');
  assert.deepEqual(errors,[]);console.log('PASS: name search, duplicate-name station selection, grouped cards, route details, precomputed 300m nearby selection, filters, mobile, empty/error states and 03:00 future semantics');
 }finally{if(browser)await browser.close();server.kill();fs.rmSync(root,{recursive:true,force:true})}
})().catch(e=>{console.error(e);process.exitCode=1});
