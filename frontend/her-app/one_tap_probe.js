const { chromium } = require('@playwright/test');
(async() => {
  const browser = await chromium.launch({headless:true});
  const page = await browser.newPage();
  page.on('request', req => { if (req.url().includes('/api/gateway/')) console.log('REQ', req.method(), req.url()) });
  page.on('response', async res => { if (res.url().includes('/api/gateway/')) console.log('RES', res.status(), res.url(), await res.text().catch(()=>'')) });
  await page.goto('http://127.0.0.1:3000');
  await page.getByRole('button', {name:'开始遇见'}).click();
  await page.getByRole('button', {name:'本机号码一键登录'}).click();
  await page.waitForTimeout(5000);
  console.log('BODY', await page.locator('body').innerText());
  await browser.close();
})();
