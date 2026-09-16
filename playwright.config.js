import {defineConfig,devices} from '@playwright/test';
export default defineConfig({testDir:'web/test',testMatch:'*.spec.js',fullyParallel:true,
 webServer:{command:'node tools/build_web.mjs --test && .venv/bin/python -m http.server 4174 --bind 127.0.0.1 --directory .artifacts/web-test',url:'http://127.0.0.1:4174',reuseExistingServer:false},
 use:{baseURL:'http://127.0.0.1:4174'},projects:[{name:'desktop-chromium',use:{...devices['Desktop Chrome']}},{name:'mobile-chromium',use:{...devices['Pixel 7']}},{name:'mobile-webkit',use:{...devices['iPhone 13']}}]});
