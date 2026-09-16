import {test,expect} from '@playwright/test';
const fleet={stable:{version:'1.1.0'},releases:[{version:'1.1.0',manifest:{git_commit:'abcdefff',minimum_base:'1.0.0',protocol_send:3}}],
 devices:[{id:'4133c5792f0a',name:'Consumer',board:'ESP32 V2',role:'consumer',enabled:true,report:{version:'1.0.0',base_version:'1.0.0',state:'current',protocol_send:3,protocol_receive:[3]},lastCheckIn:100000}]};
test.beforeEach(async({page})=>{await page.route('**/test-api/overview',route=>route.fulfill({json:fleet}));await page.goto('/');});
test('separates installed and desired versions; signs out cleanly',async({page})=>{
 await page.getByText('Sign in with Google').click();await expect(page.locator('#devices')).toContainText('1.0.0');
 await expect(page.locator('#devices')).toContainText('1.1.0 (latest)');
 await expect(page.locator('body')).toHaveJSProperty('scrollWidth',await page.locator('body').evaluate(e=>e.clientWidth));
 await page.getByText('Sign out',{exact:true}).click();await expect(page.locator('#fleet')).toBeHidden();
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
