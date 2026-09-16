import {test,expect} from '@playwright/test';
const fleet={stable:{version:'1.1.0'},releases:[{version:'1.1.0',manifest:{git_commit:'abcdefff',minimum_base:'1.0.0',protocol_send:3}}],
 devices:[{id:'4133c5792f0a',name:'Consumer',board:'ESP32 V2',role:'consumer',enabled:true,report:{version:'1.0.0',base_version:'1.0.0',state:'current',protocol_send:3,protocol_receive:[3]},lastCheckIn:100000}]};
test.beforeEach(async({page})=>{
 await page.route('https://profiles.example.test/avatar.svg',route=>route.fulfill({contentType:'image/svg+xml',body:'<svg xmlns="http://www.w3.org/2000/svg" width="44" height="44"><rect width="44" height="44" fill="teal"/></svg>'}));
 await page.route('**/test-api/overview',route=>route.fulfill({json:fleet}));await page.goto('/');
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
