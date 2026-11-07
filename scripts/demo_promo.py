"""Isolated promotional recording fixture; all upstream content is synthetic."""
import asyncio
import json
from pathlib import Path
import sys
import tempfile

import httpx
import uvicorn

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.config import Settings
from app.main import create_app

POST = '''这是一段演示资料，不代表真实校园信息。

**我的一周安排**

先确认课表，再把需要办理的事项集中记下来。空余时间熟悉校园，给自己留一点调整的空间。

![一周安排示意图](https://image.fduhole.com/i/demo/first-week.png)
'''
ANSWER = '''可以先从这三件事开始：

**确认课表和办事安排。** 把课程、材料和办理时间列在一起，具体要求以学校正式通知为准。[W1]

**参考同学的适应经验。** 有同学会先熟悉校园，再逐步调整学习节奏；这属于个人经验，可以按自己的情况取舍。[C1]

**留一点空白。** 不必把第一周排满。你可以继续告诉我最关心的事情，我再帮你细化。
'''


def completion(content=None, tool=None, arguments=None):
    message = {'role': 'assistant', 'content': content}
    if tool:
        message['tool_calls'] = [{'id': f'promo-{tool}', 'type': 'function', 'function': {
            'name': tool, 'arguments': json.dumps(arguments, ensure_ascii=False)}}]
    return httpx.Response(200, json={'choices': [{'finish_reason': 'tool_calls' if tool else 'stop', 'message': message}]})


async def upstream(request: httpx.Request) -> httpx.Response:
    if request.url.host == 'api.tavily.com':
        await asyncio.sleep(1)
        return httpx.Response(200, json={'results': [{'title': '新生办事指南（演示资料）',
            'url': 'https://example.org/demo/campus-guide', 'content': '演示资料：建议先核对课表和通知，再整理个人待办清单。实际安排请以学校发布的信息为准。'}]})
    if request.url.host == 'forum.fduhole.com':
        await asyncio.sleep(.7)
        if request.url.path == '/api/holes/12':
            return httpx.Response(200, json={'id': 12, 'time_created': '2026-11-01T00:00:00Z', 'reply': 1})
        return httpx.Response(200, json=[{'id': 34, 'hole_id': 12, 'content': POST, 'time_created': '2026-11-01T00:00:00Z'}])
    if request.url.host != 'api.deepseek.com':
        raise AssertionError('Recording fixture refuses unexpected upstream hosts')
    await asyncio.sleep(.8)
    messages = json.loads(request.content)['messages']
    if messages[-1]['role'] == 'user' and messages[-1]['content'].startswith('{'):
        return completion('{"corrections": [], "facts": []}')
    start = max(i for i, message in enumerate(messages) if message['role'] == 'user')
    question = messages[start]['content']
    if '三条待办' in question:
        return completion('可以，先做这三件事：\n\n1. 核对课表，记下需要确认的事项。\n2. 整理办事材料，逐项核对正式通知。[W1]\n3. 给熟悉校园和休息留出时间。\n\n后续再按你的实际安排调整。')
    used = {call['function']['name'] for message in messages[start:] for call in message.get('tool_calls', [])}
    sequence = [
        ('plan_research', {'questions': ['新生如何安排第一周'], 'gaps': ['公开资料与同学经验'], 'next_action': 'search', 'sources': ['web', 'campus']}),
        ('search_web', {'query': '新生办事指南'}),
        ('search_campus_posts', {'query': '第一周'}),
        ('read_campus_thread', {'hole_id': 12}),
    ]
    for name, args in sequence:
        if name not in used:
            return completion(tool=name, arguments=args)
    return completion(ANSWER)


if __name__ == '__main__':
    # A fresh disposable directory prevents touching personal history or credentials.
    with tempfile.TemporaryDirectory(prefix='ask-danta-promo-') as directory:
        folder = Path(directory)
        auth = folder / 'synthetic-auth.json'
        auth.write_text(json.dumps({'access': 'promo-synthetic-access', 'refresh': 'promo-synthetic-refresh'}))
        settings = Settings(_env_file=None, model_api_key='promo-synthetic-model', search_provider='tavily',
            search_api_key='promo-synthetic-search', campus_auth_file=auth, session_db_file=folder / 'history' / 'chat.sqlite3',
            answer_review_enabled=True, request_budget_seconds=60)
        print('PROMO FIXTURE: synthetic content only; no live upstream requests.', flush=True)
        uvicorn.run(create_app(settings, httpx.MockTransport(upstream)), host='127.0.0.1', port=8008, access_log=False)
