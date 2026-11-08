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
async function chooseSource(page: Page, name: string) {
  await page.getByRole('button', { name: /^搜索范围：/ }).click();
  await page.getByRole('menuitemradio', { name, exact: true }).click();
}
test.beforeEach(async ({ page, request }) => {
  await clean(request);
  await page.goto('/');
  await expect(page.getByRole('textbox', { name: '你的问题或追问' })).toBeEnabled();
});

test('source menu supports keyboard selection and stays within desktop and narrow viewports', async ({ page }) => {
  const trigger = page.getByRole('button', { name: /^搜索范围：/ });
  await trigger.focus();
  await trigger.press('ArrowDown');
  await expect(page.getByRole('menuitemradio', { name: '自动选择' })).toBeFocused();
  await page.keyboard.press('End');
  await expect(page.getByRole('menuitemradio', { name: '网页 + 树洞', exact: true })).toBeFocused();
  await page.keyboard.press('Home');
  await page.keyboard.press('ArrowDown');
  await page.keyboard.press('Enter');
  await expect(page.getByRole('button', { name: '搜索范围：仅网页', exact: true })).toBeFocused();
  for (const viewport of [{ width: 1440, height: 960 }, { width: 390, height: 844 }, { width: 320, height: 450 }]) {
    await page.setViewportSize(viewport);
    await trigger.click();
    const menu = page.getByRole('menu', { name: '搜索范围' });
    await expect(menu).toBeVisible();
    await expect(page.getByRole('menuitemradio', { name: '仅网页', exact: true })).toHaveAttribute('aria-checked', 'true');
    const bounds = (await menu.boundingBox())!;
    expect(bounds.x).toBeGreaterThanOrEqual(0);
    expect(bounds.y).toBeGreaterThanOrEqual(0);
    expect(bounds.x + bounds.width).toBeLessThanOrEqual(viewport.width);
    expect(bounds.y + bounds.height).toBeLessThanOrEqual(viewport.height);
    if (viewport.width > 320) await page.screenshot({ path: `../.private/verification/stage6/source-picker-${viewport.width > 760 ? 'desktop' : 'mobile'}.png` });
    await page.keyboard.press('Escape');
    await expect(menu).toHaveCount(0);
    await expect(trigger).toBeFocused();
  }
  await trigger.click();
  await page.mouse.click(315, 10);
  await expect(page.getByRole('menu')).toHaveCount(0);
  await expect(trigger).toHaveText('仅网页');
  await trigger.click();
  await page.keyboard.press('Tab');
  await expect(page.getByRole('menu')).toHaveCount(0);
  await expect(trigger).not.toBeFocused();
});

test('live execution steps update before the answer and survive refresh', async ({ page }) => {
  await page.getByRole('textbox', { name: '你的问题或追问' }).fill('查执行记录');
  await page.getByRole('button', { name: '发送', exact: true }).click();
  const progress = page.getByRole('region', { name: '回答执行记录' });
  await expect(progress.getByRole('status')).toHaveText('理解问题与已有资料');
  await progress.getByRole('button').click();
  await expect(progress.getByRole('status')).toHaveText('搜索公开网页');
  await expect(page.locator('.assistant')).toHaveCount(0);
  for (const viewport of [{ width: 1440, height: 960 }, { width: 390, height: 844 }]) {
    await page.setViewportSize(viewport);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: `../.private/verification/stage6/progress-${viewport.width}.png` });
  }
  await expect(progress.getByText('返回 1 条资料')).toBeVisible();
  await expect(page.locator('.assistant')).toHaveCount(1);
  await expect(progress.getByRole('button')).toHaveAttribute('aria-expanded', 'false');
  await progress.getByRole('button').click();
  await expect(progress.locator('.progress-step')).toHaveCount(3);
  await expect(progress.getByText('搜索公开网页', { exact: true })).toBeVisible();
  await page.reload();
  await progress.getByRole('button').click();
  await expect(progress.getByText('返回 1 条资料')).toBeVisible();
  await expect(progress.locator('.step-running')).toHaveCount(0);
});

test('desktop layout, cited Markdown, refresh, rename and deletion', async ({ page, context }) => {
  await page.setViewportSize({ width: 1440, height: 960 });
  await expect(page).toHaveTitle('Ask Danta');
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
  await page.getByRole('menuitem', { name: '重命名', exact: true }).click();
  await page.getByRole('textbox', { name: '对话名称' }).fill('办事资料');
  await page.getByRole('button', { name: '保存名称' }).click();
  await expect(page.getByRole('button', { name: '办事资料', exact: true })).toBeVisible();
  await page.screenshot({ path: '../.private/verification/stage6/desktop-answer.png' });
  await page.getByRole('button', { name: '收起历史会话' }).click();
  await expect(page.locator('aside.sidebar')).toHaveCount(0);
  await expect(page.getByRole('button', { name: '新对话', exact: true })).toBeVisible();
  await page.getByRole('button', { name: '展开历史会话' }).click();
  await page.getByRole('button', { name: '管理对话：办事资料' }).click();
  await page.getByRole('menuitem', { name: '删除', exact: true }).click();
  await page.getByRole('button', { name: '确认删除' }).click();
  await expect(page.getByRole('heading', { name: '今天，有什么校园问题？' })).toBeVisible();
  await expect(page.locator('.history-row')).toHaveCount(0);
});

test('lowercase campus citations open real source cards and preserve code text', async ({ page }) => {
  await page.route('**/api/sessions/*', async route => {
    const response = await route.fetch();
    const data = await response.json();
    if (route.request().method() === 'GET' && Array.isArray(data.messages)) {
      for (const message of data.messages) {
        if (message.role !== 'assistant') continue;
        message.content = '选课建议[c121]，另一处引用[C121]。不存在[c999]。代码 `[c121]`。';
        message.sources = [{ id: 'C121', source: 'campus', title: '合成资料', snippet: '用于检查引用关联的合成摘录', hole_id: 12, floor_id: 34, is_mock: false, published_at: null, truncated: false }];
      }
    }
    await route.fulfill({ response, json: data });
  });
  await ask(page, '检查引用');
  const citations = page.getByRole('button', { name: '查看引用 C121', exact: true });
  await expect(citations).toHaveCount(2);
  await expect(page.locator('.markdown code')).toHaveText('[c121]');
  await expect(page.getByRole('button', { name: '查看引用 C999', exact: true })).toHaveCount(0);
  for (const viewport of [{ width: 1440, height: 960 }, { width: 390, height: 844 }]) {
    await page.setViewportSize(viewport);
    await citations.first().click();
    await expect(page.locator('.source-card.selected')).toContainText('用于检查引用关联的合成摘录');
    await page.screenshot({ path: `../.private/verification/stage6/citation-${viewport.width}.png` });
    await page.getByRole('button', { name: '收起来源并返回回答' }).click();
    await expect(citations.first()).toBeFocused();
  }
  await page.reload();
  await expect(citations).toHaveCount(2);
});

test('drafts and source preference stay with their conversation', async ({ page }) => {
  await ask(page, '第一段聊天');
  await chooseSource(page, '仅网页');
  await page.getByRole('textbox', { name: '你的问题或追问' }).fill('未发送的追问');
  await page.getByRole('button', { name: '新对话', exact: true }).click();
  await expect(page.getByRole('button', { name: /^搜索范围：自动/ })).toBeVisible();
  await ask(page, '第二段聊天');
  await page.getByRole('button', { name: '第一段聊天', exact: true }).click();
  await expect(page.getByRole('textbox', { name: '你的问题或追问' })).toHaveValue('未发送的追问');
  await expect(page.getByRole('button', { name: '搜索范围：仅网页', exact: true })).toBeVisible();
  await expect(page.locator('.user')).toHaveCount(1);
});

test('history actions float without resizing rows and remain usable in the mobile drawer', async ({ page, request }) => {
  for (let index = 1; index <= 16; index++) {
    const session = await (await request.post('/api/sessions')).json();
    await request.patch(`/api/sessions/${session.session_id}`, { data: { title: `校园问题 ${index}` } });
  }
  await page.reload();
  const menu = page.getByRole('menu', { name: /^对话操作：/ });
  for (const viewport of [{ width: 1440, height: 960 }, { width: 390, height: 844 }, { width: 320, height: 450 }]) {
    await page.setViewportSize(viewport);
    if (viewport.width < 760) {
      if (!await page.getByRole('dialog', { name: '历史会话' }).isVisible()) await page.getByRole('button', { name: '展开历史会话' }).click();
      await expect(page.getByRole('dialog', { name: '历史会话' })).toBeVisible();
    }
    const row = page.locator('.history-row').last();
    const trigger = row.getByRole('button', { name: /^管理对话：/ });
    await trigger.scrollIntoViewIfNeeded();
    const before = (await row.boundingBox())!;
    await trigger.click();
    await expect(menu).toBeVisible();
    await expect(page.getByRole('menuitem', { name: '重命名', exact: true })).toBeFocused();
    const after = (await row.boundingBox())!;
    expect(after.height).toBe(before.height);
    expect(after.y).toBe(before.y);
    const box = (await menu.boundingBox())!;
    expect(box.x).toBeGreaterThanOrEqual(0);
    expect(box.y).toBeGreaterThanOrEqual(0);
    expect(box.x + box.width).toBeLessThanOrEqual(viewport.width);
    expect(box.y + box.height).toBeLessThanOrEqual(viewport.height);
    if (viewport.width > 320) await page.screenshot({ path: `../.private/verification/stage6/history-menu-${viewport.width}.png` });
    await page.keyboard.press('ArrowDown');
    await expect(page.getByRole('menuitem', { name: '删除', exact: true })).toBeFocused();
    await page.keyboard.press('Escape');
    await expect(menu).toHaveCount(0);
    await expect(trigger).toBeFocused();
    if (viewport.width < 760) await expect(page.getByRole('dialog', { name: '历史会话' })).toBeVisible();
    await trigger.press('ArrowUp');
    await expect(page.getByRole('menuitem', { name: '删除', exact: true })).toBeFocused();
    await page.keyboard.press('Home');
    await expect(page.getByRole('menuitem', { name: '重命名', exact: true })).toBeFocused();
    await page.keyboard.press('Tab');
    await expect(menu).toHaveCount(0);
    await trigger.click();
    await page.locator('.brand').click();
    await expect(menu).toHaveCount(0);
    await trigger.click();
    await page.locator('.history').evaluate(element => element.dispatchEvent(new Event('scroll')));
    await expect(menu).toHaveCount(0);
  }
  await page.locator('.history-more').last().click();
  await page.getByRole('menuitem', { name: '重命名', exact: true }).click();
  await expect(page.getByRole('dialog', { name: '重命名对话' })).toBeVisible();
  await expect(page.getByRole('dialog', { name: '历史会话' })).toHaveCount(0);
  await page.getByRole('textbox', { name: '对话名称' }).fill('菜单修改成功');
  await page.getByRole('button', { name: '保存名称' }).click();
  await page.getByRole('button', { name: '展开历史会话' }).click();
  await expect(page.getByRole('button', { name: '菜单修改成功', exact: true })).toBeVisible();
});

test('campus Markdown images load on expansion and handle broken or unsupported addresses', async ({ page }) => {
  const imageUrl = 'https://image.fduhole.com/i/2024/08/25/66caeb1790d81.jpg';
  const brokenUrl = 'https://image.fduhole.com/i/2024/08/25/missing.png';
  const requested: string[] = [];
  page.on('request', request => { if (request.resourceType() === 'image') requested.push(request.url()); });
  await page.route('https://image.fduhole.com/**', route => route.request().url() === imageUrl
    ? route.fulfill({ contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360"><rect width="640" height="360" fill="#edf4fb"/><rect x="32" y="32" width="576" height="296" rx="8" fill="white"/><text x="60" y="95" font-family="sans-serif" font-size="26" fill="#00529b">Synthetic campus attachment</text><path d="M60 140H570M60 200H570M60 260H570" stroke="#dbeafb" stroke-width="10"/></svg>' })
    : route.fulfill({ status: 404, body: 'not found' }));
  await page.route('**/api/sessions/*', async route => {
    const response = await route.fetch();
    const data = await response.json();
    if (route.request().method() === 'GET' && Array.isArray(data.messages)) {
      for (const message of data.messages) {
        if (message.role !== 'assistant') continue;
        message.content = '参考树洞配图[C1]。';
        message.sources = [{ id: 'C1', source: 'campus', title: '合成图片资料', snippet: `**配图说明**\n\n![](${imageUrl})\n\n![失效配图](${brokenUrl})\n\n![外站](https://example.org/blocked.png)\n\n![伪装域名](https://image.fduhole.com.example.org/blocked.png)\n\n![内网](http://127.0.0.1/private.png)\n\n\`![](${imageUrl})\`\n\n<img src="https://example.org/raw.png">`, hole_id: 12, floor_id: 34, is_mock: false, published_at: null, truncated: false }];
      }
    }
    await route.fulfill({ response, json: data });
  });
  await ask(page, '检查配图');
  expect(requested.filter(url => url.startsWith('https://image.fduhole.com/'))).toHaveLength(0);
  await page.getByRole('button', { name: '查看引用 C1', exact: true }).click();
  const picture = page.getByRole('img', { name: '树洞帖子配图', exact: true });
  await picture.scrollIntoViewIfNeeded();
  await expect.poll(() => picture.evaluate((img: HTMLImageElement) => img.naturalWidth)).toBe(640);
  await expect(picture).toHaveAttribute('referrerpolicy', 'no-referrer');
  await expect(page.getByText('失效配图加载失败', { exact: false })).toBeVisible();
  await expect(page.locator('.source-markdown code')).toHaveText(`![](${imageUrl})`);
  expect(requested.filter(url => /blocked\.png|raw\.png|private\.png/.test(url))).toEqual([]);
  for (const viewport of [{ width: 1440, height: 960 }, { width: 390, height: 844 }]) {
    await page.setViewportSize(viewport);
    await picture.scrollIntoViewIfNeeded();
    const box = (await picture.boundingBox())!;
    expect(box.x).toBeGreaterThanOrEqual(0);
    expect(box.x + box.width).toBeLessThanOrEqual(viewport.width);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: `../.private/verification/stage6/campus-image-${viewport.width}.png` });
  }
});

test('switching cancels a running answer and preserves its question', async ({ page }) => {
  await page.getByRole('textbox', { name: '你的问题或追问' }).fill('等待合成回答');
  await page.getByRole('button', { name: '发送', exact: true }).click();
  await expect(page.getByRole('button', { name: '停止回答' })).toBeVisible();
  await expect(page.getByRole('button', { name: /^搜索范围：/ })).toBeDisabled();
  await page.getByRole('button', { name: '新对话', exact: true }).click();
  await page.getByRole('button', { name: '停止并切换', exact: true }).click();
  await expect(page.getByRole('heading', { name: '今天，有什么校园问题？' })).toBeVisible();
  await page.getByRole('button', { name: '等待合成回答', exact: true }).click();
  await expect(page.getByRole('textbox', { name: '你的问题或追问' })).toHaveValue('等待合成回答');
  await expect(page.getByRole('region', { name: '回答执行记录' }).getByRole('button')).toContainText('回答已停止');
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
  await page.getByRole('button', { name: '账号', exact: true }).click();
  await page.getByRole('button', { name: '登录树洞', exact: true }).click();
  await page.getByLabel('树洞邮箱').fill('synthetic@example.org');
  await page.getByLabel('树洞密码').fill('wrong-synthetic-password');
  await page.getByRole('button', { name: '登录', exact: true }).click();
  await expect(page.getByLabel('树洞密码')).toBeEmpty();
  await expect(page.locator('.campus-login .error')).toBeVisible();
  await page.getByRole('button', { name: '关闭设置', exact: true }).click();
  await expect(page.getByRole('textbox', { name: '你的问题或追问' })).toHaveValue('登录失败后保留的草稿');
  await page.getByRole('textbox', { name: '你的问题或追问' }).fill('');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: '../.private/verification/stage6/mobile-answer.png' });
  await page.setViewportSize({ width: 390, height: 450 });
  await expect.poll(async () => {
    const box = (await page.getByRole('textbox', { name: '你的问题或追问' }).boundingBox())!;
    return box.y + box.height;
  }).toBeLessThan(450);
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
  await expect(page.getByRole('region', { name: '回答执行记录' }).getByRole('status')).toHaveText('理解问题与已有资料');
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
  await page.getByRole('button', { name: '重新发送', exact: true }).click();
  await expect(page.locator('.assistant')).toHaveCount(1);
  await expect(page.locator('.user')).toHaveCount(1);
});

test('rechecking a committed answer removes the stale failed message', async ({ page }) => {
  await page.route(/\/api\/sessions\/[^/]+$/, route => route.request().method() === 'GET'
    ? route.fulfill({ status: 503, json: { error: { message: '合成会话读取故障' } } }) : route.continue(), { times: 1 });
  await page.getByRole('textbox', { name: '你的问题或追问' }).fill('已保存但尚未同步的问题');
  await page.getByRole('button', { name: '发送', exact: true }).click();
  await expect(page.locator('.user.failed')).toHaveCount(1);
  await page.getByRole('button', { name: '重新检查', exact: true }).click();
  await expect(page.locator('.assistant')).toHaveCount(1);
  await expect(page.locator('.user')).toHaveCount(1);
  await expect(page.locator('.user.failed')).toHaveCount(0);
  await expect(page.getByRole('textbox', { name: '你的问题或追问' })).toBeEmpty();
});

test('copy and edit a user message into a new conversation', async ({ page, context, request }) => {
  await ask(page, '原始问题');
  const original = (await (await request.get('/api/sessions')).json()).sessions[0].session_id;
  await context.grantPermissions(['clipboard-read', 'clipboard-write']);
  await page.locator('.user').hover();
  await page.getByRole('button', { name: '复制消息', exact: true }).click();
  expect(await page.evaluate(() => navigator.clipboard.readText())).toBe('原始问题');
  await page.getByRole('button', { name: '编辑并重新发送' }).click();
  await page.getByRole('textbox', { name: '编辑消息', exact: true }).fill('修改后的问题');
  await page.getByRole('button', { name: '取消', exact: true }).click();
  await expect(page.locator('.user p')).toHaveText('原始问题');
  await page.locator('.user').hover();
  await page.getByRole('button', { name: '编辑并重新发送' }).click();
  await page.getByRole('textbox', { name: '编辑消息', exact: true }).fill('修改后的问题');
  await page.getByRole('button', { name: '发送修改', exact: true }).click();
  await expect(page.locator('.user p')).toHaveText('修改后的问题');
  await expect(page.locator('.assistant')).toHaveCount(1);
  expect((await (await request.get(`/api/sessions/${original}`)).json()).messages[0].content).toBe('原始问题');
  await page.reload();
  await expect(page.locator('.user p')).toHaveText('修改后的问题');
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 900 });
    await page.locator('.user').hover();
    await page.getByRole('button', { name: '编辑并重新发送' }).click();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: `../.private/verification/stage6/message-edit-${width}.png` });
    await page.getByRole('button', { name: '取消', exact: true }).click();
  }
});

test('an incomplete model answer retries in place without creating a sidebar conversation', async ({ page, request }) => {
  await ask(page, '失败一次');
  const before = (await (await request.get('/api/sessions')).json()).sessions;
  expect(before).toHaveLength(1);
  const original = before[0].session_id;
  await page.getByRole('button', { name: '重新发送', exact: true }).click();
  await expect(page.locator('.assistant')).toHaveCount(1);
  await expect(page.locator('.assistant')).toContainText('合成验收回答');
  await expect(page.getByRole('button', { name: '重新发送', exact: true })).toHaveCount(0);
  const after = (await (await request.get('/api/sessions')).json()).sessions;
  expect(after).toHaveLength(1);
  expect(after[0].session_id).toBe(original);
  const saved = await (await request.get(`/api/sessions/${original}`)).json();
  expect(saved.messages).toHaveLength(2);
  await page.reload();
  await expect(page.locator('.assistant')).toContainText('合成验收回答');
  await expect(page.locator('.user')).toHaveCount(1);
});

test('settings preserve conversation and login enables a consented data-source choice', async ({ page }) => {
  await ask(page, '设置前的聊天');
  await page.getByRole('button', { name: '设置', exact: true }).click();
  await expect(page.getByRole('button', { name: '清空当前对话', exact: true })).toHaveCount(0);
  await page.getByRole('button', { name: '关闭设置', exact: true }).click();
  await page.reload();
  await expect(page.locator('.assistant')).toHaveCount(1);
  await page.getByRole('button', { name: '设置', exact: true }).click();
  await page.getByRole('button', { name: '账号', exact: true }).click();
  await page.getByRole('button', { name: '登录树洞', exact: true }).click();
  await page.getByLabel('树洞邮箱').fill('synthetic@example.org');
  await page.getByLabel('树洞密码').fill('synthetic-password');
  await page.getByRole('button', { name: '登录', exact: true }).click();
  await expect(page.locator('.login-success')).toBeVisible();
  await expect(page.getByLabel('树洞密码')).toHaveCount(0);
  await page.getByRole('button', { name: '关闭设置', exact: true }).click();
  await chooseSource(page, '网页 + 树洞');
  await page.getByRole('button', { name: '允许使用', exact: true }).click();
  await expect(page.getByRole('button', { name: '搜索范围：网页 + 树洞', exact: true })).toBeVisible();
  await chooseSource(page, '仅网页');
  await page.reload();
  await expect(page.getByRole('button', { name: '搜索范围：仅网页', exact: true })).toBeVisible();
  const storage = await page.evaluate(() => JSON.stringify({ local: { ...localStorage }, session: { ...sessionStorage } }));
  expect(storage).not.toContain('synthetic-password');
  expect(storage).not.toContain('synthetic-access');
});
