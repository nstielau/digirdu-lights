import {test,expect} from '@playwright/test';
const fleet={stable:{version:'1.1.0'},releases:[{version:'1.1.0',manifest:{git_commit:'abcdefff',minimum_base:'1.0.0',protocol_send:3}}],
 devices:[{id:'4133c5792f0a',name:'Consumer',board:'ESP32 V2',role:'consumer',enabled:true,report:{version:'1.0.0',base_version:'1.0.0',state:'current',protocol_send:3,protocol_receive:[3]},lastCheckIn:100000}]};
test.beforeEach(async({page})=>{
 await page.route('https://profiles.example.test/avatar.svg',route=>route.fulfill({contentType:'image/svg+xml',body:'<svg xmlns="http://www.w3.org/2000/svg" width="44" height="44"><rect width="44" height="44" fill="teal"/></svg>'}));
 await page.route('**/test-api/telemetry',route=>route.fulfill({json:{batches:[]}}));
 await page.route('**/test-api/overview',route=>route.fulfill({json:fleet}));await page.goto('/');
});
test('fleet subtabs sit below the hero and switch by click and keyboard',async({page})=>{
 await page.getByText('Sign in with Google').click();
 const tabs=page.getByRole('tablist',{name:'Fleet sections'});
 await expect(tabs.getByRole('tab')).toHaveText(['Releases','Devices','Session Telemetry']);
 await expect(tabs.getByRole('tab',{name:'Devices'})).toHaveAttribute('aria-selected','true');
 await expect(page.getByRole('tabpanel',{name:'Devices'})).toBeVisible();
 await expect(page.getByRole('tabpanel',{name:'Releases'})).toBeHidden();
 await expect(page.locator('#devices .card').first()).toContainText('No RF uploads for this device among the 40 most recent fleet uploads.');
 await expect(tabs).toHaveJSProperty('scrollWidth',await tabs.evaluate(e=>e.clientWidth));
 const below=await tabs.evaluate(e=>e.getBoundingClientRect().top);
 const heroBottom=await page.locator('.page-heading').evaluate(e=>e.getBoundingClientRect().bottom);
 expect(below).toBeGreaterThanOrEqual(heroBottom);
 await tabs.getByRole('tab',{name:'Session Telemetry'}).click();
 await expect(page.getByRole('tabpanel',{name:'Session Telemetry'})).toBeVisible();
 await tabs.getByRole('tab',{name:'Session Telemetry'}).press('Home');
 await expect(tabs.getByRole('tab',{name:'Releases'})).toBeFocused();
 await expect(page.getByRole('tabpanel',{name:'Releases'})).toBeVisible();
 await page.getByRole('button',{name:'Refresh reports'}).click();
 await expect(page.getByRole('tabpanel',{name:'Releases'})).toBeVisible();
});
test('device card shows recent RF diagnostics and an honest missing-producer state',async({page})=>{
 const counts={features:710,controls:182,rejected:52,native_drops:0,link_losses:22,
  skipped:0,audio_overruns:0,audio_discontinuities:0};
 await page.route('**/test-api/telemetry',route=>route.fulfill({json:{batches:[
  {device_id:'4133c5792f0a',receivedAt:100000,record:{role:'consumer',windows:[],counts,
   rssi:{mean:-81,min:-92,max:-69},truncated_windows:0,epoch_uncertain:false}}
 ]}}));
 await page.getByText('Sign in with Google').click();
 const card=page.locator('#devices .card').first();
 await expect(card).toContainText('Accepted features');
 await expect(card).toContainText('710');
 await expect(card).toContainText('Latest RSSI');
 await expect(card).toContainText('-81 dBm');
 await expect(card).toContainText('RSSI history');
 await expect(card).toContainText('mean of 1 upload');
 await expect(card).toContainText('Producer upload needed');
 await expect(card).toContainText('Rejected packets');
 await expect(card).toContainText('52');
});
test('fleet shows historical RF gaps and unobserved nodes',async({page})=>{
 const zero='00'.repeat(32),mask='1e'+zero.slice(2),received='12'+zero.slice(2);
 const w=(fields)=>({session:7,base:0,received:zero,attempted:zero,delivered:zero,failed:zero,controls:zero,...fields});
 const counts={features:0,controls:0,skipped:0,rejected:0,native_drops:2,link_losses:1,audio_overruns:0,audio_discontinuities:0};
 const batches=[
  {device_id:'producer',receivedAt:100000,record:{role:'producer',windows:[w({attempted:mask,delivered:mask})],counts,epoch_uncertain:false,rssi:null,truncated_windows:0}},
  {device_id:'4133c5792f0a',receivedAt:101000,record:{role:'consumer',windows:[w({received})],counts,epoch_uncertain:false,rssi:{min:-80,max:-70,mean:-75},truncated_windows:0}}
 ];
 await page.route('**/test-api/telemetry',route=>route.fulfill({json:{batches}}));
 await page.getByText('Sign in with Google').click();
 await expect(page.locator('#devices .device-rf')).toContainText('2/4 (50%)');
 await page.getByRole('tab',{name:'Session Telemetry'}).click();
 await expect(page.locator('#telemetry')).toContainText('missing 2');
 await expect(page.locator('#telemetry')).toContainText('native drops 2');
 await expect(page.locator('#telemetry')).toContainText('RSSI -75 dBm');
});
test('separates installed and desired versions; signs out cleanly',async({page})=>{
 await page.getByText('Sign in with Google').click();await expect(page.locator('#devices')).toContainText('1.0.0');
 await expect(page.locator('#devices')).toContainText('1.1.0 (latest)');
 await expect(page.locator('body')).toHaveJSProperty('scrollWidth',await page.locator('body').evaluate(e=>e.clientWidth));
 await expect(page.getByText('Sign out',{exact:true})).toBeHidden();
 await page.getByRole('button',{name:'Open account menu'}).click();
 await page.getByText('Sign out',{exact:true}).click();await expect(page.locator('#fleet')).toBeHidden();
 await expect(page.locator('#profile')).toBeHidden();await expect(page.locator('#sign-in')).toBeFocused();
});
test('pin sends explicit version and fresh request ID',async({page})=>{
 let request;await page.route('**/test-api/change',async route=>{request=route.request().postDataJSON();await route.fulfill({json:{ok:true}});});
 await page.getByText('Sign in with Google').click();await page.getByText('Assign release').click();
 await expect(page.locator('#status')).toContainText('Saved.');expect(request.action).toBe('pin');expect(request.version).toBe('1.1.0');expect(request.requestId).toHaveLength(36);
});
test('failed mutation is not retried automatically',async({page})=>{
 let calls=0;await page.route('**/test-api/change',route=>{calls++;return route.fulfill({status:503,body:'unavailable'});});
 await page.getByText('Sign in with Google').click();await page.getByText('Pause updates').click();
 await expect(page.locator('#status')).toContainText('could not be confirmed');expect(calls).toBe(1);
});
test('device names render as text',async({page})=>{
 await page.route('**/test-api/overview',route=>route.fulfill({json:{...fleet,devices:[{...fleet.devices[0],name:'<img src=x onerror=alert(1)>'}]}}));
 await page.getByText('Sign in with Google').click();await expect(page.locator('h3')).toHaveText('<img src=x onerror=alert(1)>');await expect(page.locator('#devices img')).toHaveCount(0);
});
test('profile photo opens a keyboard-accessible account dropdown',async({page})=>{
 await page.getByText('Sign in with Google').click();
 const toggle=page.getByRole('button',{name:'Open account menu'});
 await expect(page.locator('#profile-photo')).toBeVisible();
 await expect(page.locator('#profile-photo')).toHaveJSProperty('naturalWidth',44);
 await toggle.focus();await page.keyboard.press('Enter');
 await expect(toggle).toHaveAttribute('aria-expanded','true');
 await expect(page.locator('#profile-menu')).toContainText('owner@example.test');
 await page.keyboard.press('ArrowDown');await expect(page.locator('#sign-out')).toBeFocused();
 await page.keyboard.press('Escape');await expect(page.locator('#profile-menu')).toBeHidden();await expect(toggle).toBeFocused();
 await toggle.click();await page.getByRole('heading',{name:'Devices',exact:true}).click();
 await expect(page.locator('#profile-menu')).toBeHidden();
});
test('unavailable photo falls back to initials',async({page})=>{
 await page.route('https://profiles.example.test/avatar.svg',route=>route.abort());
 await page.getByText('Sign in with Google').click();
 await expect(page.locator('#profile-initials')).toHaveText('TO');await expect(page.locator('#profile-photo')).toBeHidden();
 await page.getByRole('button',{name:'Open account menu'}).click();await expect(page.locator('#sign-out')).toBeVisible();
});
test('effects guide has direct navigation and shares the signed-in account',async({page})=>{
 await page.getByText('Sign in with Google').click();
 await page.getByRole('navigation',{name:'Main',exact:true}).getByRole('link',{name:'Effects'}).click();
 await expect(page).toHaveTitle('Effects · Digirdu Lights');
 for(const name of ['Spectrum','Ember','Aurora','Ripple'])await expect(page.getByRole('heading',{name,exact:true})).toBeVisible();
 await expect(page.locator('tbody tr')).toHaveCount(8);
 await expect(page.locator('body')).toHaveJSProperty('scrollWidth',await page.locator('body').evaluate(e=>e.clientWidth));
 await page.getByRole('button',{name:'Open account menu'}).click();await page.getByRole('button',{name:'Sign out',exact:true}).click();
 await page.getByRole('navigation',{name:'Main',exact:true}).getByRole('link',{name:'Fleet',exact:true}).click();
 await expect(page.locator('#fleet')).toBeHidden();await expect(page.locator('#sign-in')).toBeVisible();
});
test('effects guide works when opened directly without sign-in',async({page})=>{
 let requests=0;await page.route('**/test-api/**',route=>{requests++;return route.abort();});
 await page.goto('/effects.html');await expect(page.getByRole('heading',{name:'Spectrum',exact:true})).toBeVisible();
 await expect(page.locator('#sign-in')).toBeVisible();expect(requests).toBe(0);
});
test('saved replay plays, pauses, seeks and labels its synthetic tail',async({page})=>{
 await page.goto('/effects.html');
 const play=page.getByRole('button',{name:'Play replay',exact:true}), seek=page.getByRole('slider',{name:'Position'});
 await expect(play).toBeEnabled();await expect(page.locator('#replay-grids canvas')).toHaveCount(5);
 await expect(page.getByRole('heading',{name:'Chroma',exact:true})).toBeVisible();
 await expect(page.locator('.effect-notes')).toContainText('Keep effects 1–4 selected until every board reports 1.0.4');
 await expect(page.locator('body')).toHaveJSProperty('scrollWidth',await page.locator('body').evaluate(e=>e.clientWidth));
 await seek.fill('450');await seek.dispatchEvent('input');
 await expect(page.locator('#replay-section')).toHaveText('drone');
 await expect(page.locator('#replay-time')).toContainText('22.5');
 await play.click();await expect.poll(()=>seek.inputValue()).not.toBe('450');
 await page.getByRole('button',{name:'Pause replay'}).click();
 const paused=await seek.inputValue();await page.waitForTimeout(150);expect(await seek.inputValue()).toBe(paused);
 await seek.fill(await seek.getAttribute('max'));await seek.dispatchEvent('input');
 await expect(page.locator('#replay-section')).toContainText('synthetic fade (not recorded)');
 await play.click();await expect.poll(async()=>Number(await seek.inputValue())).toBeLessThan(100);
});
test('missing replay keeps the effect guide usable',async({page})=>{
 await page.route('**/effects-replay.json',route=>route.fulfill({status:503,body:'unavailable'}));
 await page.goto('/effects.html');
 await expect(page.locator('#replay-section')).toContainText('could not load');
 await expect(page.getByRole('button',{name:'Play replay'})).toBeDisabled();
 await expect(page.getByRole('heading',{name:'Chroma',exact:true})).toBeVisible();
});
