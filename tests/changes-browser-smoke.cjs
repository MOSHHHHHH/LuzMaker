/* Real Chromium integration against files produced by the production pipeline. */
const assert=require('node:assert/strict');
const {spawn,execFileSync}=require('node:child_process');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {chromium}=require('playwright');
(async()=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'lzm-changes-ui-'));
 const python=`
import sys
from pathlib import Path
from datetime import date
sys.path.insert(0,'tests')
from test_changes_gtfs import make_zip
from scripts.changes_pipeline import run
root=Path(sys.argv[1]);z=root/'feed.zip'
make_zip(z);run(z,root/'state.sqlite.gz',root/'data/changes',date(2026,11,13))
make_zip(z,extra_stop=True);run(z,root/'state.sqlite.gz',root/'data/changes',date(2026,11,13))
`;
 execFileSync('python',['-c',python,root],{stdio:'pipe'});
 fs.copyFileSync('changes.html',path.join(root,'changes.html'));
 const server=spawn('python',['-m','http.server','8765','--bind','127.0.0.1','--directory',root],{stdio:'ignore'});
 let browser;
 try{
  browser=await chromium.launch({executablePath:process.env.CHROME_BIN||'/usr/bin/chromium',headless:true,args:['--no-sandbox']});
  const page=await browser.newPage();await page.clock.install({time:new Date('2026-11-13T12:00:00Z')});const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto('http://127.0.0.1:8765/changes.html');
  await page.locator('#station').fill('123');await page.locator('#station').press('Enter');
  await page.waitForFunction(()=>document.querySelectorAll('#results article').length>0);
  assert.match(await page.locator('#freshness').innerText(),/2026/);
  await page.locator('summary').first().click();assert.match(await page.locator('.new').first().innerText(),/125/);
  await page.selectOption('#category','removed');assert.equal(await page.locator('#results article').count(),0);
  await page.selectOption('#category','route_changed');assert.ok(await page.locator('#results article').count()>0);
  await page.selectOption('#period','future');assert.ok(await page.locator('#results article').count()>0);assert.match(await page.locator('#results article h3').first().innerText(),/צפוי/);
  await page.selectOption('#period','current');assert.ok(await page.locator('#results article').count()>0);
  await page.selectOption('#period','all');
  await page.setViewportSize({width:375,height:812});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  await page.locator('#station').fill('999999');await page.locator('#station').press('Enter');
  await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('אין שינויים'));
  await page.route('**/stations/*.json',r=>r.fulfill({status:500,body:'error'}));
  await page.locator('#station').fill('124');await page.locator('#station').press('Enter');
  await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('נסו שוב'));
  assert.deepEqual(errors,[]);
  console.log('Station changes browser checks passed: generated JSON, Enter search, route expansion, filtering, mobile, empty and error states');
 }finally{if(browser)await browser.close();server.kill();fs.rmSync(root,{recursive:true,force:true})}
})().catch(e=>{console.error(e);process.exitCode=1});
