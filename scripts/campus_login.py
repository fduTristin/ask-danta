"""Interactive project-owned FDUHole login; never accept passwords on the command line."""

import asyncio
import getpass
from pathlib import Path
import sys
import warnings

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import httpx
from pydantic import ValidationError

from app.campus import CampusService
from app.campus_auth import CampusError
from app.config import Settings


async def login(email: str, password: str) -> None:
    settings = Settings()
    async with httpx.AsyncClient(trust_env=False) as client:
        await CampusService(settings, client).login(email, password)


def main() -> int:
    try:
        email = input("树洞登录邮箱：").strip()
        if not email or len(email) > 320 or "@" not in email:
            print("请输入有效邮箱。", file=sys.stderr)
            return 1
        # Do not fall back to echoed input when a terminal cannot hide a password.
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            password = getpass.getpass("树洞密码（不显示、不保存）：")
        if not password:
            print("密码不能为空。", file=sys.stderr)
            return 1
        try:
            asyncio.run(login(email, password))
        finally:
            password = ""
        print("登录成功，token 已保存至本项目配置的凭据文件，并限制为当前用户访问。")
        return 0
    except CampusError as exc:
        print(f"登录失败 [{exc.code}]：{exc.message}", file=sys.stderr)
    except (EOFError, KeyboardInterrupt):
        print("登录已取消。", file=sys.stderr)
    except getpass.GetPassWarning:
        print("当前终端不能隐藏密码，请在本机交互终端运行。", file=sys.stderr)
    except ValidationError:
        print("本地配置格式无效，请检查 .env。", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
