// Actual browser interactions against the disposable demo_promo.py backend.
// Run after npm install: node scripts/record_promo.mjs
import { createRequire } from 'node:module';
import { readFile, mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawn } from 'node:child_process';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const require = createRequire(path.join(root, 'frontend/package.json'));
const { chromium } = require('@playwright/test');
const output = path.join(root, '.private/promo');
const media = path.join(root, 'docs/media');
await mkdir(output, { recursive: true });
await mkdir(media, { recursive: true });
const children = [];
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
async function ready(url) {
  for (let attempt = 0; attempt < 80; attempt++) {
    try { if ((await fetch(url)).ok) return; } catch {}
    if (children.some(child => child.exitCode !== null)) throw new Error('Recording server exited');
    await sleep(250);
  }
  throw new Error(`Recording server unavailable: ${url}`);
}
// Never attach to an existing server or reuse its data.
for (const port of [8008, 5178]) {
  try { await fetch(`http://127.0.0.1:${port}`, { signal: AbortSignal.timeout(500) }); throw new Error(`Port ${port} is already occupied`); }
  catch (error) { if (error.message.includes('occupied')) throw error; }
}
let browser;
let recordingPage;
try {
  children.push(spawn(path.join(root, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python'), ['scripts/demo_promo.py'], { cwd: root, windowsHide: true, stdio: 'inherit' }));
  children.push(spawn(process.execPath, ['node_modules/vite/bin/vite.js'], { cwd: path.join(root, 'frontend'), windowsHide: true, stdio: 'inherit', env: { ...process.env, BACKEND_PORT: '8008', FRONTEND_PORT: '5178' } }));
  await ready('http://127.0.0.1:8008/api/health');
  await ready('http://127.0.0.1:5178/');
  browser = await chromium.launch({ channel: 'chrome', headless: true });
  const context = await browser.newContext({ viewport: { width: 1920, height: 1080 }, recordVideo: { dir: output, size: { width: 1920, height: 1080 } }, deviceScaleFactor: 1 });
  await context.addInitScript(() => { try { localStorage.setItem('danta-campus-consent', '1'); } catch {} });
  const seed = await context.request.post('http://127.0.0.1:8008/api/sessions');
  const seedId = (await seed.json()).session_id;
  await context.request.patch(`http://127.0.0.1:8008/api/sessions/${seedId}`, { data: { title: '我的校园待办' } });
  const pageCreated = Date.now();
  const page = await context.newPage();
  recordingPage = page;
  page.on('pageerror', error => console.error('Browser error:', error.message));
  await page.route('https://image.fduhole.com/i/demo/first-week.png', route => route.fulfill({ contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="800" height="300"><rect width="800" height="300" rx="16" fill="#edf4fb"/><text x="35" y="58" font-family="Microsoft YaHei,sans-serif" font-size="26" fill="#00529b">我的第一周 · 演示配图</text><g font-family="Microsoft YaHei,sans-serif" font-size="22" fill="#416581"><rect x="30" y="90" width="225" height="170" rx="12" fill="white"/><rect x="287" y="90" width="225" height="170" rx="12" fill="white"/><rect x="544" y="90" width="225" height="170" rx="12" fill="white"/><text x="55" y="140">学习</text><text x="55" y="195">核对课表</text><text x="312" y="140">办事</text><text x="312" y="195">整理材料</text><text x="569" y="140">生活</text><text x="569" y="195">熟悉校园</text></g></svg>' }));
  const stage = await readFile(path.join(root, 'scripts/promo-stage.html'), 'utf8');
  await page.route('http://127.0.0.1:5178/__promo', route => route.fulfill({ contentType: 'text/html', body: stage }));
  await page.goto('http://127.0.0.1:5178/__promo');
  const app = page.frameLocator('#app');
  await app.getByRole('textbox', { name: '你的问题或追问' }).waitFor();
  await app.getByRole('button', { name: '我的校园待办', exact: true }).waitFor();
  const start = Date.now();
  const chapters = [];
  const mark = async (title, caption, percent) => {
    chapters.push({ seconds: (Date.now() - start) / 1000, title, caption });
    await page.evaluate(({ title, caption, percent }) => {
      document.querySelector('#headline').textContent = title;
      document.querySelector('#caption').textContent = caption;
      document.querySelector('#rail').style.width = `${percent}%`;
    }, { title, caption, percent });
    console.log(`Scene: ${title}`);
  };
  const click = async locator => {
    // The pending response is remounted once its newly created session arrives.
    for (let attempt = 0; ; attempt++) {
      try { await locator.scrollIntoViewIfNeeded(); break; }
      catch (error) { if (attempt >= 2 || !error.message.includes('not attached')) throw error; await sleep(100); }
    }
    const box = await locator.boundingBox();
    const x = box.x + box.width / 2, y = box.y + box.height / 2;
    await page.evaluate(({ x, y }) => { const cursor = document.querySelector('#cursor'); cursor.style.opacity = '1'; cursor.style.transform = `translate(${x}px,${y}px)`; }, { x, y });
    await page.mouse.move(x, y, { steps: 10 });
    await sleep(350);
    await page.evaluate(() => { const pulse = document.querySelector('#pulse'); pulse.classList.remove('click'); void pulse.offsetWidth; pulse.classList.add('click'); });
    await locator.click();
  };
  await page.screenshot({ path: path.join(media, 'ask-danta-poster.png') });
  await sleep(2600);
  await page.evaluate(() => document.querySelector('#cover').classList.add('hidden'));
  await mark('校园问题，直接问。', '按需要选择公开网页，或一起参考树洞经验。', 10);
  await click(app.getByRole('button', { name: /^搜索范围：/ }));
  await sleep(1000);
  await click(app.getByRole('menuitemradio', { name: '网页 + 树洞', exact: true }));
  const input = app.getByRole('textbox', { name: '你的问题或追问' });
  await click(input);
  await input.pressSequentially('刚到江湾校区，怎么安排第一周的学习和生活？', { delay: 65 });
  await sleep(400);
  await click(app.getByRole('button', { name: '发送', exact: true }));
  await mark('每一步，都看得见。', '搜索、读取与核对，执行状态实时更新。', 30);
  await app.getByRole('region', { name: '回答执行记录' }).getByRole('status').filter({ hasText: '理解问题与已有资料' }).waitFor();
  await click(app.getByRole('region', { name: '回答执行记录' }).getByRole('button'));
  await app.locator('.assistant').waitFor({ state: 'visible', timeout: 25000 });
  await mark('答案之外，还有依据。', '点开引用，区分公开资料与同学的个人经验。', 55);
  await sleep(1700);
  await click(app.getByRole('button', { name: '查看引用 W1', exact: true }));
  await sleep(1900);
  await click(app.getByRole('button', { name: '收起来源并返回回答' }));
  await click(app.getByRole('button', { name: '查看引用 C1', exact: true }));
  const photo = app.getByRole('img', { name: '一周安排示意图' });
  await photo.scrollIntoViewIfNeeded();
  await photo.evaluate(image => image.decode());
  await photo.evaluate(image => image.scrollIntoView({ block: 'center', behavior: 'instant' }));
  await mark('经验与配图，一起查看。', '直接阅读引用片段，查看帖子里的配图。', 70);
  await sleep(2400);
  await click(app.getByRole('button', { name: '收起来源并返回回答' }));
  await mark('继续追问，细化你的安排。', '保留对话上下文，把问题一步步问清楚。', 82);
  await click(input);
  await input.pressSequentially('帮我整理成三条待办。', { delay: 65 });
  await click(app.getByRole('button', { name: '发送', exact: true }));
  await app.locator('.assistant').nth(1).waitFor({ state: 'visible', timeout: 15000 });
  await sleep(1600);
  await mark('留住对话，随时回来。', '历史记录保存在本机，重命名和整理都很方便。', 94);
  await click(app.getByRole('button', { name: /^管理对话：刚到江湾/ }));
  await sleep(1800);
  await page.keyboard.press('Escape');
  await page.evaluate(() => {
    document.querySelector('#cursor').style.opacity = '0';
    document.querySelector('#cover-title').innerHTML = '校园里的问题，<br>有据可查。';
    document.querySelector('#cover-subtitle').textContent = '问问旦挞 · 查资料，看依据，接着问。';
    document.querySelector('#cover-play').textContent = '在 README 中开始体验';
    document.querySelector('#cover').classList.remove('hidden');
    document.querySelector('#rail').style.width = '100%';
  });
  await sleep(3000);
  const duration = (Date.now() - start) / 1000;
  const video = page.video();
  await context.close();
  await writeFile(path.join(output, 'recording.json'), JSON.stringify({ raw: await video.path(), trim_start: (start - pageCreated) / 1000, duration, chapters }, null, 2));
  console.log(`Recording complete: ${duration.toFixed(1)} seconds`);
} catch (error) {
  if (recordingPage && !recordingPage.isClosed()) {
    await recordingPage.screenshot({ path: path.join(output, 'recording-error.png') });
    console.error(await recordingPage.frameLocator('#app').locator('body').innerText().catch(() => 'Frame unavailable'));
  }
  throw error;
} finally {
  await browser?.close();
  for (const child of children.reverse()) {
    // Windows Python's venv launcher has a child; terminate only our process tree.
    if (process.platform === 'win32' && child.pid) {
      await new Promise(resolve => { const stop = spawn('taskkill', ['/PID', String(child.pid), '/T', '/F'], { windowsHide: true, stdio: 'ignore' }); stop.on('close', resolve); });
    } else child.kill('SIGTERM');
  }
}
