"""Compare review modes on synthetic evidence using the configured live model."""
import argparse
import asyncio
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))

import httpx
from pydantic import ValidationError

from app.answer import AnswerAudit, audit_fact_errors, review_payload
from app.model import ModelError, ModelService
from app.prompts import AUDIT
from app.runtime_settings import load_settings


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true', required=True, help='Consumes model quota; no real user or campus data is sent')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Output already exists; use a new path to preserve the previous measurement')
    settings = load_settings().model_copy(update={'model_max_tokens': 16384, 'model_timeout_seconds': 90})
    cases = [
        ('wrong_channel', '电子证明收费吗？', '电子证明每份收费8元。[W1]', '纸质证明每份8元；电子证明免费。', True),
        ('supported', '甲平台的GPU怎么申请？', '甲平台的 GPU 需通过平台提交申请，由导师审核。[W1]', '甲平台提供GPU。用户通过平台提交申请，由导师审核。', False),
    ]
    rows = []
    async with httpx.AsyncClient(trust_env=False) as client:
        for index, (case, question, draft, evidence, needs_correction) in enumerate(cases):
            sources = [{'id': 'W1', 'source': 'web', 'title': '合成服务说明', 'snippet': evidence, 'is_mock': False}]
            sources.extend({'id': f'W{i}', 'source': 'web', 'title': f'无关的合成服务{i}', 'is_mock': False,
                            'snippet': f'这是另一个对象的合成说明，与当前问题无关。服务{i}仅用于性能测试。' * 8} for i in range(2, 25))
            payload = review_payload(question, [], sources, 0, draft, None)
            payload.update(available_tools=[], required_actions=[], missing_actions=[], retrieval_forbidden=True)
            messages = [{'role': 'system', 'content': AUDIT}, {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False)}]
            # Rotate order to reduce systematic warmup bias. This is a small
            # diagnostic sample, not a stable latency or quality benchmark.
            modes = ['high', 'low', 'disabled'] if index == 0 else ['disabled', 'low', 'high']
            for mode in modes:
                configured = settings.model_copy(update={'model_thinking': 'disabled' if mode == 'disabled' else 'enabled',
                                                        'model_reasoning_effort': 'low' if mode == 'disabled' else mode})
                started = time.monotonic()
                row = {'case': case, 'mode': mode, 'model': configured.model_name, 'passed': False}
                try:
                    message = await ModelService(configured, client).complete(messages, [])
                    audit = AnswerAudit.model_validate_json(message.content)
                    row.update(usage=message.usage, passed=bool(audit.corrections) == needs_correction and not audit_fact_errors(audit, payload))
                except ModelError as exc:
                    row['error'] = exc.code
                except ValidationError:
                    row['error'] = 'invalid_audit'
                row['seconds'] = round(time.monotonic() - started, 3)
                rows.append(row)
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(json.dumps({'data': 'synthetic evidence only; real model calls', 'results': rows}, ensure_ascii=False, indent=2), encoding='utf-8')
                print(json.dumps(row), flush=True)


if __name__ == '__main__':
    asyncio.run(main())
