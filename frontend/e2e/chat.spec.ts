import { test, expect } from '@playwright/test';
import type { Page, APIRequestContext } from '@playwright/test';

async function clean(request: APIRequestContext) {
  const result = await (await request.get('/api/sessions')).json();
  for (const item of result.sessions) await request.delete(`/api/sessions/${item.session_id}`);
}
async function ask(page: Page, text: string) {
  await page.getByRole('textbox', { name: '你的问题或追问' }).fill(text);
  await page.getByRole('button', { name: '发送', exact: true }).click();
  await expect(page.locator('.assistant')).toHaveCount(1);
  await expect(page.getByRole('textbox', { name: '你的问题或追问' })).toBeEmpty();
}
test.beforeEach(async ({ page, request }) => {
  await clean(request);
  await page.goto('/');
  await expect(page.getByRole('textbox', { name: '你的问题或追问' })).toBeEnabled();
});

test('desktop layout, cited Markdown, refresh, rename and deletion', async ({ page, context }) => {
  await page.setViewportSize({ width: 1440, height: 960 });
  await expect(page).toHaveTitle('问问旦挞');
  for (const label of ['服务状态', '当前进度', '试一次网页搜索']) await expect(page.getByText(label, { exact: true })).toHaveCount(0);
  await page.screenshot({ path: '../.private/verification/stage6/desktop-empty.png' });
  await ask(page, '查合成来源');
  await context.grantPermissions(['clipboard-read', 'clipboard-write']);
  await page.getByRole('button', { name: '复制回答', exact: true }).click();
  await expect(page.getByRole('button', { name: '已复制回答', exact: true })).toBeVisible();
  expect(await page.evaluate(() => navigator.clipboard.readText())).toContain('[W1]');
  await expect(page.locator('.markdown table')).toBeVisible();
  await page.getByRole('button', { name: '查看引用 W1' }).click();
  await expect(page.getByRole('link', { name: '合成验收来源' })).toBeVisible();
  await page.getByRole('button', { name: '收起来源并返回回答' }).click();
  await expect(page.getByRole('button', { name: '查看引用 W1' })).toBeFocused();
  await page.reload();
  await expect(page.locator('.assistant')).toHaveCount(1);
  await page.getByRole('button', { name: '管理对话：查合成来源' }).click();
  await page.getByRole('button', { name: '重命名', exact: true }).click();
  await page.getByRole('textbox', { name: '对话名称' }).fill('办事资料');
  await page.getByRole('button', { name: '保存名称' }).click();
  await expect(page.getByRole('button', { name: '办事资料', exact: true })).toBeVisible();
  await page.screenshot({ path: '../.private/verification/stage6/desktop-answer.png' });
  await page.getByRole('button', { name: '收起历史会话' }).click();
  await expect(page.locator('aside.sidebar')).toHaveCount(0);
  await expect(page.getByRole('button', { name: '新对话', exact: true })).toBeVisible();
  await page.getByRole('button', { name: '展开历史会话' }).click();
  await page.getByRole('button', { name: '管理对话：办事资料' }).click();
  await page.getByRole('button', { name: '删除', exact: true }).click();
  await page.getByRole('button', { name: '确认删除' }).click();
  await expect(page.getByRole('heading', { name: '今天，有什么校园问题？' })).toBeVisible();
  await expect(page.locator('.history-row')).toHaveCount(0);
});

test('drafts and source preference stay with their conversation', async ({ page }) => {
  await ask(page, '第一段聊天');
  await page.getByRole('combobox', { name: '允许使用的数据源' }).selectOption('web');
  await page.getByRole('textbox', { name: '你的问题或追问' }).fill('未发送的追问');
  await page.getByRole('button', { name: '新对话', exact: true }).click();
  await expect(page.getByRole('combobox')).toHaveValue('auto');
  await ask(page, '第二段聊天');
  await page.getByRole('button', { name: '第一段聊天', exact: true }).click();
  await expect(page.getByRole('textbox', { name: '你的问题或追问' })).toHaveValue('未发送的追问');
  await expect(page.getByRole('combobox')).toHaveValue('web');
  await expect(page.locator('.user')).toHaveCount(1);
});

test('switching cancels a running answer and preserves its question', async ({ page }) => {
  await page.getByRole('textbox', { name: '你的问题或追问' }).fill('等待合成回答');
  await page.getByRole('button', { name: '发送', exact: true }).click();
  await expect(page.getByRole('button', { name: '停止回答' })).toBeVisible();
  await page.getByRole('button', { name: '新对话', exact: true }).click();
  await page.getByRole('button', { name: '停止并切换', exact: true }).click();
  await expect(page.getByRole('heading', { name: '今天，有什么校园问题？' })).toBeVisible();
  await page.getByRole('button', { name: '等待合成回答', exact: true }).click();
  await expect(page.getByRole('textbox', { name: '你的问题或追问' })).toHaveValue('等待合成回答');
  await expect(page.locator('.assistant')).toHaveCount(0);
  await expect(page.getByRole('textbox', { name: '你的问题或追问' })).toBeEnabled();
});

test('mobile drawer, login failure, safe Markdown and keyboard', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.locator('aside.sidebar')).toHaveCount(0);
  await page.getByRole('textbox', { name: '你的问题或追问' }).fill('输入法');
  await page.getByRole('textbox', { name: '你的问题或追问' }).dispatchEvent('keydown', { key: 'Enter', code: 'Enter', isComposing: true });
  await expect(page.locator('.assistant')).toHaveCount(0);
  await page.getByRole('textbox', { name: '你的问题或追问' }).press('Shift+Enter');
  await expect(page.getByRole('textbox', { name: '你的问题或追问' })).toHaveValue('输入法\n');
  await ask(page, '查来源安全排版');
  await expect(page.locator('.markdown code')).toHaveText('[W1]');
  await expect(page.locator('.markdown')).toContainText('危险链接');
  await expect(page.locator('.markdown script')).toHaveCount(0);
  await expect(page.locator('.markdown a[href^="javascript:"]')).toHaveCount(0);
  expect(await page.evaluate(() => (window as unknown as { unsafeExecuted?: boolean }).unsafeExecuted)).toBeUndefined();
  await page.getByRole('textbox', { name: '你的问题或追问' }).fill('登录失败后保留的草稿');
  await page.getByRole('button', { name: '展开历史会话' }).click();
  await expect(page.getByRole('dialog', { name: '历史会话' })).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('button', { name: '展开历史会话' })).toBeFocused();
  await page.getByRole('button', { name: '展开历史会话' }).click();
  await page.getByRole('button', { name: '设置', exact: true }).click();
  await page.getByRole('button', { name: '登录树洞', exact: true }).click();
  await page.getByLabel('树洞邮箱').fill('synthetic@example.org');
  await page.getByLabel('树洞密码').fill('wrong-synthetic-password');
  await page.getByRole('button', { name: '登录并保存凭据' }).click();
  await expect(page.getByLabel('树洞密码')).toBeEmpty();
  await expect(page.locator('.campus-login .error')).toBeVisible();
  await page.getByRole('button', { name: '关闭设置', exact: true }).click();
  await expect(page.getByRole('textbox', { name: '你的问题或追问' })).toHaveValue('登录失败后保留的草稿');
  await page.getByRole('textbox', { name: '你的问题或追问' }).fill('');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: '../.private/verification/stage6/mobile-answer.png' });
  await page.setViewportSize({ width: 390, height: 450 });
  const box = await page.getByRole('textbox', { name: '你的问题或追问' }).boundingBox();
  expect(box!.y + box!.height).toBeLessThan(450);
});

test('reading old messages does not jump on a new response', async ({ page }) => {
  await ask(page, '长回答');
  await page.getByRole('textbox', { name: '你的问题或追问' }).fill('等待回答');
  await page.getByRole('button', { name: '发送', exact: true }).click();
  await expect(page.getByRole('button', { name: '停止回答' })).toBeVisible();
  await page.locator('.messages-scroll').evaluate(element => { element.scrollTop = 0; });
  await expect(page.getByRole('button', { name: '回到最新' })).toBeVisible();
  await expect(page.locator('.assistant')).toHaveCount(2, { timeout: 25_000 });
  expect(await page.locator('.messages-scroll').evaluate(element => element.scrollTop)).toBeLessThan(100);
});

test('lost final response restores the committed answer without duplicate retry', async ({ page }) => {
  await page.route('**/api/sessions/*/chat', async route => {
    await route.fetch(); // Backend has committed; simulate losing the entire response.
    await route.abort('connectionreset');
  }, { times: 1 });
  await ask(page, '提交后断线');
  await expect(page.locator('.user')).toHaveCount(1);
  await page.reload();
  await expect(page.locator('.assistant')).toHaveCount(1);
  await expect(page.getByRole('textbox', { name: '你的问题或追问' })).toBeEmpty();
});

test('restoring a busy conversation clears the submitted question when it completes', async ({ page, request }) => {
  const session = await (await request.post('/api/sessions')).json();
  const completion = request.post(`/api/sessions/${session.session_id}/chat`, { data: { message: '等待恢复中的回答', source_mode: 'web' } });
  await expect.poll(async () => (await (await request.get(`/api/sessions/${session.session_id}`)).json()).busy).toBe(true);
  await page.evaluate(id => localStorage.setItem('danta-current-session', id), session.session_id);
  await page.reload();
  await expect(page.getByRole('textbox', { name: '你的问题或追问' })).toHaveValue('等待恢复中的回答');
  await expect(page.getByRole('button', { name: '停止回答' })).toBeVisible();
  await completion;
  await expect(page.locator('.assistant')).toHaveCount(1);
  await expect(page.getByRole('textbox', { name: '你的问题或追问' })).toBeEmpty();
  await expect(page.getByRole('textbox', { name: '你的问题或追问' })).toBeEnabled();
});

test('failed send preserves the draft through recheck and can retry', async ({ page }) => {
  await page.route('**/api/sessions/*/chat', route => route.fulfill({ status: 503, json: { error: { message: '合成暂时故障' } } }), { times: 1 });
  await page.getByRole('textbox', { name: '你的问题或追问' }).fill('需要保留的问题');
  await page.getByRole('button', { name: '发送', exact: true }).click();
  await expect(page.getByRole('button', { name: '重试', exact: true })).toBeVisible();
  await page.getByRole('button', { name: '重新检查', exact: true }).click();
  await expect(page.getByRole('textbox', { name: '你的问题或追问' })).toHaveValue('需要保留的问题');
  await page.getByRole('button', { name: '发送', exact: true }).click();
  await expect(page.locator('.assistant')).toHaveCount(1);
});

test('clear persists and login success enables a consented data-source choice', async ({ page }) => {
  await ask(page, '清空前的聊天');
  await page.getByRole('button', { name: '设置', exact: true }).click();
  await page.getByRole('button', { name: '清空当前对话', exact: true }).click();
  await page.getByRole('button', { name: '确认删除' }).click();
  await page.reload();
  await expect(page.locator('.assistant')).toHaveCount(0);
  await page.getByRole('button', { name: '设置', exact: true }).click();
  await page.getByRole('button', { name: '登录树洞', exact: true }).click();
  await page.getByLabel('树洞邮箱').fill('synthetic@example.org');
  await page.getByLabel('树洞密码').fill('synthetic-password');
  await page.getByRole('button', { name: '登录并保存凭据' }).click();
  await expect(page.locator('.login-success')).toBeVisible();
  await expect(page.getByLabel('树洞密码')).toHaveCount(0);
  await page.getByRole('button', { name: '关闭设置', exact: true }).click();
  await page.getByRole('combobox').selectOption('all');
  await page.getByRole('button', { name: '允许使用', exact: true }).click();
  await expect(page.getByRole('combobox')).toHaveValue('all');
  await page.getByRole('combobox').selectOption('web');
  await page.reload();
  await expect(page.getByRole('combobox')).toHaveValue('web');
  const storage = await page.evaluate(() => JSON.stringify({ local: { ...localStorage }, session: { ...sessionStorage } }));
  expect(storage).not.toContain('synthetic-password');
  expect(storage).not.toContain('synthetic-access');
});
