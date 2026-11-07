"""Isolated stage-six browser fixture. No local credentials or external requests."""
import asyncio
import json
from pathlib import Path
import sys

import httpx
import uvicorn

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.config import Settings
from app.main import create_app


async def upstream(request: httpx.Request) -> httpx.Response:
    if request.url.host == "auth.fduhole.com":
        body = json.loads(request.content)
        if body.get('password') != 'synthetic-password':
            return httpx.Response(401, json={"detail": "synthetic invalid credentials"})
        return httpx.Response(200, json={"access": "synthetic-access", "refresh": "synthetic-refresh"})
    if request.url.host == "api.tavily.com":
        if '执行记录' in request.content.decode():
            await asyncio.sleep(2)
        return httpx.Response(200, json={"results": [{"title": "合成验收来源", "url": "https://example.org/ux-verification", "content": "合成验收资料：提交申请后查看办理进度，不代表真实学校政策。"}]})
    if request.url.host != "api.deepseek.com":
        raise AssertionError("Unexpected fixture endpoint")
    body = json.loads(request.content)
    messages = body['messages']
    user_index = max(i for i, item in enumerate(messages) if item['role'] == 'user')
    question = messages[user_index]['content']
    if '执行记录' in question:
        await asyncio.sleep(2)
    if '等待' in question:
        await asyncio.sleep(20)
    if '失败一次' in question and not getattr(upstream, 'failed_once', False):
        upstream.failed_once = True
        raise httpx.ConnectError('synthetic outage')
    needs_search = '查' in question or '来源' in question
    tool = next((item for item in messages[user_index:] if item['role'] == 'tool'), None)
    if needs_search and not tool and body.get('tools'):
        message = {"role": "assistant", "content": None, "tool_calls": [{"id": "fixture-search", "type": "function", "function": {"name": "search_web", "arguments": '{"query":"合成验收"}'}}]}
        if '执行记录' in question:
            message['tool_calls'][0]['function']['arguments'] = '{"query":"执行记录"}'
    else:
        citation = ''
        if tool:
            results = json.loads(tool['content']).get('results', [])
            if results:
                citation = ' [' + results[0]['id'] + ']'
        answer = '这是**合成验收回答**，不代表真实学校政策。\n\n提交申请后查看办理进度。' + citation + '\n\n| 项目 | 说明 |\n| --- | --- |\n| 材料 | 以正式通知为准 |\n| 渠道 | 核对学校网站 |\n\n你可以继续补充校区或证明类型。'
        if '长回答' in question:
            answer += '\n\n' + '\n\n'.join(f'### 示例段落 {i}\n\n这里是用于检查阅读与滚动的合成文字，不提供真实办事结论。' for i in range(1, 25))
        if '安全排版' in question:
            answer += '\n\n<script>window.unsafeExecuted=true</script>\n\n[危险链接](javascript:alert(1))\n\n`[W1]`'
        message = {"role": "assistant", "content": answer}
    return httpx.Response(200, json={"choices": [{"finish_reason": "tool_calls" if message.get('tool_calls') else "stop", "message": message}]})


def fixture_app():
    fixture_auth = ROOT / '.private/verification/stage6/auth.json'
    if fixture_auth.exists():
        if json.loads(fixture_auth.read_text(encoding='utf-8')).get('access') != 'synthetic-access':
            raise RuntimeError('Refuse to replace non-fixture credentials')
        fixture_auth.unlink()
    app = create_app(Settings(_env_file=None, model_api_key='synthetic-model-key', search_provider='tavily',
        search_api_key='synthetic-search-key', campus_auth_file=fixture_auth,
        session_db_file=ROOT / '.private/verification/stage6/history/chat.sqlite3', answer_review_enabled=False),
        transport=httpx.MockTransport(upstream))
    return app


if __name__ == '__main__':
    print('SYNTHETIC UX FIXTURE ONLY: no live model, search or campus requests.', flush=True)
    uvicorn.run(fixture_app(), host='127.0.0.1', port=8006, access_log=False)
