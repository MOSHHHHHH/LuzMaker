'use strict';
const assert=require('node:assert/strict'),{spawn,execFileSync}=require('node:child_process'),fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {chromium}=require('playwright');
(async()=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'lzm-tools-'));
 execFileSync('python',['-m','tests.make_ui_fixture',root],{stdio:'pipe'});
 const server=spawn('python',['-m','http.server','8767','--bind','127.0.0.1','--directory',path.join(root,'site')],{stdio:'ignore'});let browser;
 try{
  browser=await chromium.launch({executablePath:process.env.CHROME_BIN||'/usr/bin/chromium',args:['--no-sandbox']});const page=await browser.newPage();await page.clock.install({time:new Date('2026-11-13T12:00:00Z')});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));await page.addInitScript(()=>{window.print=()=>{throw Error('PDF must never invoke browser printing')}});
  await page.goto('http://127.0.0.1:8767/index.html');await page.waitForFunction(()=>catalog?.lines?.length);await page.locator('#newGroup').click();assert.equal(await page.locator('#groupName').getAttribute('placeholder'),'למשל: קווים מביתר לתל אביב');
  await page.locator('#groupName').fill('ביתר לתל אביב (ABC)');await page.locator('#groupSearch').fill('101');await page.locator('#groupSuggestions button').filter({hasText:'קו 101'}).click();
  await page.waitForFunction(()=>!document.querySelector('#stopSelect').disabled);await page.selectOption('#stopSelect','A');await page.locator('#addLine').click();
  await page.locator('#selectedLines summary').click();await page.waitForSelector('.station-option');
  assert.equal(await page.locator('.station-option').count(),20,'Already-added variant excluded and duplicate platforms coalesced');
  const choices=page.locator('.station-option');await choices.filter({hasText:/^100\s/}).locator('input').check();await choices.filter({hasText:/^102\s/}).locator('input').check();await page.locator('[data-station-add]').click();
  assert.equal(await page.locator('#selectedLines .line-entry').count(),3);
  await page.locator('#saveGroup').click();await page.waitForFunction(()=>!document.querySelector('#generate').classList.contains('hidden'));
  await page.locator('#generate').click();await page.waitForSelector('#printPdf');
  // Inspect actual application state, not a synthetic second implementation.
  const group=await page.evaluate(()=>selectedGroup);assert.equal(group.lines.length,3);assert.equal(group.lines.find(x=>x.number==='100').stopIds.length,2);
  await page.route('**/assets/pdf/LuzSans-Regular.ttf',r=>r.fulfill({status:503,body:'temporary'}));await page.locator('#printPdf').click();await page.waitForFunction(()=>document.querySelector('#pdfStatus').textContent.includes('לא ניתן'));assert.equal(await page.locator('#printPdf').isEnabled(),true);
  await page.unroute('**/assets/pdf/LuzSans-Regular.ttf');
  const downloadPromise=page.waitForEvent('download');await page.locator('#printPdf').click();const download=await downloadPromise;const file=path.join(root,'browser.pdf');await download.saveAs(file);assert.equal(fs.readFileSync(file).subarray(0,5).toString(),'%PDF-');
  assert.match(await page.locator('#pdfStatus').innerText(),/נוצר והורד/);
  const csvPromise=page.waitForEvent('download');await page.locator('#allCsv').click();const csv=await csvPromise;const csvPath=path.join(root,'browser.csv');await csv.saveAs(csvPath);const content=fs.readFileSync(csvPath,'utf8');assert.match(content,/שם הלוח/);assert.match(content,/08:30/,'Combined-platform departure is retained');assert.match(content,/08:10/);
  if(process.env.LZM_SCREENSHOT_DIR)fs.copyFileSync(file,path.join(process.env.LZM_SCREENSHOT_DIR,'browser-export.pdf'));

  // A station-first search keeps equal-name physical stations separate and
  // fixes the selected public code, including all of its platform IDs.
  await page.locator('#homeResults').click();await page.locator('#newGroup').click();
  await page.locator('#groupSearch').fill('תחנה מרכזית');await page.waitForSelector('#groupSuggestions:not([hidden])');
  assert.equal(await page.locator('#groupSuggestions button').count(),2,'Same-name stations remain distinct');
  await page.locator('#groupSearch').press('ArrowDown');await page.locator('#groupSearch').press('Enter');
  await page.waitForSelector('#routeCards .route-card');await page.locator('#routeFilter').fill('100');assert.equal(await page.locator('#routeCards .route-card').count(),1,'Station routes can be filtered before choosing a line');await page.locator('#routeFilter').fill('');assert.match(await page.locator('#searchSelection').innerText(),/12345/);
  await page.locator('#routeCards .route-card').filter({has:page.locator('.line-number',{hasText:/^100$/})}).click();
  assert.equal(await page.locator('#stopSelect').inputValue(),'A');assert.equal(await page.locator('#stopSelect').isDisabled(),true);
  await page.locator('#addLine').click();assert.equal((await page.evaluate(()=>working[0])).stopIds.length,2);
  await page.setViewportSize({width:375,height:812});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  page.once('dialog',dialog=>dialog.dismiss());await page.locator('#cancelEdit').click();assert.equal(await page.locator('#editor').isVisible(),true,'Unsaved work survives cancelling exit');
  assert.deepEqual(errors,[]);console.log('PASS: exact-stop multi-select, platform coalescing, persisted group, timetable generation, direct JS PDF/font retry, and CSV');
 }finally{if(browser)await browser.close();server.kill();fs.rmSync(root,{recursive:true,force:true})}
})().catch(e=>{console.error(e);process.exitCode=1});
