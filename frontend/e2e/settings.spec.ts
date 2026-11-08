import { test, expect } from '@playwright/test';

test('settings save without restart, preserve secrets and support clearing', async ({ page, request }) => {
  const original = await (await request.get('/api/settings')).json();
  const { model_api_key_configured, search_api_key_configured, ...restore } = original;
  try {
    await page.goto('/');
    await page.getByRole('button', { name: '设置', exact: true }).click();
    await expect(page.getByLabel('模型 API Key', { exact: true })).toBeEmpty();
    await page.getByLabel('模型名称', { exact: true }).fill('synthetic-updated-model');
    await page.getByLabel('模型 API Key', { exact: true }).fill('synthetic-updated-key');
    const saved = page.waitForResponse(response => response.url().endsWith('/api/settings') && response.request().method() === 'PATCH');
    await page.getByRole('button', { name: '保存', exact: true }).click();
    expect((await saved).status()).toBe(200);
    await expect(page.getByText('设置已保存', { exact: true })).toBeVisible();
    await expect(page.getByLabel('模型 API Key', { exact: true })).toBeEmpty();
    expect((await (await request.get('/api/health')).json()).model.name).toBe('synthetic-updated-model');
    await page.getByRole('button', { name: '网页搜索', exact: true }).click();
    await page.getByLabel('搜索服务').selectOption('mock');
    await page.getByRole('button', { name: '保存', exact: true }).click();
    await expect(page.getByText('设置已保存', { exact: true })).toBeVisible();
    await page.getByRole('button', { name: '关闭设置', exact: true }).click();
    await expect(page.getByText('当前搜索使用合成样例，不能作为实际办事依据。')).toBeVisible();
    await page.reload();
    await page.getByRole('button', { name: '设置', exact: true }).click();
    await expect(page.getByLabel('模型名称', { exact: true })).toHaveValue('synthetic-updated-model');
    await expect(page.getByLabel('模型 API Key', { exact: true })).toBeEmpty();
    await page.getByRole('button', { name: '清除模型 API Key', exact: true }).click();
    await page.getByRole('button', { name: '撤销清除模型 API Key', exact: true }).click();
    await expect(page.getByRole('button', { name: '保存', exact: true })).toBeDisabled();
    await page.getByRole('button', { name: '清除模型 API Key', exact: true }).click();
    await page.getByRole('button', { name: '保存', exact: true }).click();
    await expect(page.getByText('设置已保存', { exact: true })).toBeVisible();
    await page.getByRole('button', { name: '关闭设置', exact: true }).click();
    await page.getByRole('button', { name: '配置模型', exact: true }).click();
    await expect(page.getByLabel('模型 API Key', { exact: true })).toHaveAttribute('placeholder', '输入 API Key');
    const storage = await page.evaluate(() => JSON.stringify({ ...localStorage, ...sessionStorage }));
    expect(storage).not.toContain('synthetic-updated-key');
    expect(JSON.stringify(await (await request.get('/api/settings')).json())).not.toContain('synthetic-updated-key');
  } finally {
    await request.patch('/api/settings', { data: { ...restore, model_api_key: model_api_key_configured ? 'synthetic-model-key' : '', search_api_key: search_api_key_configured ? 'synthetic-search-key' : '' } });
  }
});

test('settings layout fits desktop and narrow screens and keeps edits after failure', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: '设置', exact: true }).click();
  for (const width of [1440, 390, 320]) {
    await page.setViewportSize({ width, height: width === 320 ? 450 : 900 });
    for (const category of ['模型', '网页搜索', '账号', '高级']) {
      await page.getByRole('navigation', { name: '设置分类' }).getByRole('button', { name: category, exact: true }).click();
      const dialog = page.getByRole('dialog', { name: '设置', exact: true });
      const box = (await dialog.boundingBox())!;
      expect(box.x).toBeGreaterThanOrEqual(0);
      expect(box.x + box.width).toBeLessThanOrEqual(width);
      expect(await dialog.evaluate(node => node.scrollWidth <= node.clientWidth)).toBe(true);
      if (width !== 320) await page.screenshot({ path: `../.private/verification/stage6/settings-${category}-${width}.png` });
    }
  }
  await page.getByRole('button', { name: '模型', exact: true }).click();
  await page.getByLabel('模型名称', { exact: true }).fill('keep-unsaved-model');
  await page.route('**/api/settings', route => route.request().method() === 'PATCH' ? route.fulfill({ status: 503, json: { error: { message: '合成保存故障' } } }) : route.continue());
  await page.getByRole('button', { name: '保存', exact: true }).click();
  await expect(page.getByRole('alert')).toHaveText('合成保存故障');
  await expect(page.getByLabel('模型名称', { exact: true })).toHaveValue('keep-unsaved-model');
  await page.getByRole('button', { name: '关闭设置', exact: true }).click();
  await expect(page.getByRole('dialog', { name: '设置', exact: true })).toHaveCount(0);
});

