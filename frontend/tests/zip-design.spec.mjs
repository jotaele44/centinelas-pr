import { test, expect } from 'playwright/test';

// Explicit failure fixtures exercise chrome without reading mutable sources.
// These tests certify UI behavior only; they do not certify backend data.
test.beforeEach(async ({ page }) => {
 await page.route('**/*', async route => {
  const url = new URL(route.request().url());
  if (url.pathname.includes('public-settings')) return route.fulfill({json: {requires_auth: false}});
  if (url.hostname === '127.0.0.1' && url.port === '5419' && !url.pathname.startsWith('/api/')) return route.continue();
  return route.abort('connectionrefused');
 });
});
for (const width of [390, 1440]) {
 test(`archive design renders and stays within ${width}px viewport`, async ({ page }) => {
  await page.setViewportSize({width, height: 900});
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto('/');
  await expect(page.locator('.zip-surface')).toBeVisible();
  await expect.poll(() => page.locator('#root').innerText()).not.toBe('');
  await page.evaluate(() => document.fonts.ready);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
  expect(errors).toEqual([]);
  const css = await page.locator('.zip-surface').evaluate(el => getComputedStyle(el).getPropertyValue('--zip-background'));
  expect(css.trim()).not.toBe('');
 });
}
test('language and theme use the existing persistent preferences', async ({page}) => {
 await page.goto('/'); await expect(page.locator('.zip-surface')).toBeVisible();
 const theme=page.getByRole('button',{name:/Change theme|Cambiar tema/});
 const before=await page.locator('html').getAttribute('data-theme');await theme.click();
 await expect(page.locator('html')).not.toHaveAttribute('data-theme',before);
 await page.getByRole('button',{name:/Change language|Cambiar idioma/}).click();
 const lang=await page.evaluate(()=>localStorage.getItem('centinelas_lang'));
 await page.reload();await expect(page.locator('.zip-surface')).toBeVisible();
 expect(await page.evaluate(()=>localStorage.getItem('centinelas_lang'))).toBe(lang);
});
