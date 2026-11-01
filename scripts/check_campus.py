"""Explicit live campus check. Prints counts/IDs only, never tokens or post bodies."""

import argparse
import asyncio
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import httpx
from pydantic import ValidationError

from app.campus import CampusBudget, CampusService
from app.campus_auth import CampusError
from app.config import Settings


async def check(query: str) -> int:
    settings = Settings()
    budget = CampusBudget(settings.max_campus_pages)
    async with httpx.AsyncClient(trust_env=False) as client:
        service = CampusService(settings, client)
        async with asyncio.timeout(settings.request_budget_seconds):
            page = await service.search_campus_posts(query, limit=20, budget=budget)
            if not page.results:
                print("真实搜索响应有效，但没有可读取结果；搜索/详情联调尚未通过。")
                return 1
            hole_id = page.results[0].hole_id
            thread = await service.read_campus_thread(hole_id, limit=20, budget=budget)
            if not thread.results:
                print("帖子元数据有效，但没有可读取楼层；详情验收尚未通过。")
                return 1
            if page.next_offset is not None and budget.pages < budget.max_pages:
                await service.search_campus_posts(query, offset=page.next_offset, limit=20, budget=budget)
            print(f"真实树洞契约检查通过：search_results={len(page.results)}, hole_id={hole_id}, "
                  f"thread_floors={len(thread.results)}, pages={budget.pages}。")
            print("仅验证接口和字段，不代表正文相关性、结论质量或全量遍历已验收。")
            return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", default="图书馆")
    args = parser.parse_args()
    try:
        return asyncio.run(check(args.query))
    except CampusError as exc:
        print(f"未通过 [{exc.code}]：{exc.message}", file=sys.stderr)
    except TimeoutError:
        print("未通过：达到本轮总时长预算。", file=sys.stderr)
    except ValidationError:
        print("未通过：配置或输入格式无效。", file=sys.stderr)
    except KeyboardInterrupt:
        print("检查已取消。", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
