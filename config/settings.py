# -*- coding: utf-8 -*-
"""全局配置:Pydantic 模型 + YAML 加载 + 环境变量覆盖。

支持的环境变量(优先级高于 settings.yaml):
    PYTEST_BASE_URL   网关地址,如 http://localhost:8201
    PYTEST_TIMEOUT    单次请求超时(秒)
    PYTEST_RETRY      连接失败重试次数
    PYTEST_MEMBER_USERNAME / PYTEST_MEMBER_PASSWORD  会员账号
    PYTEST_ADMIN_USERNAME / PYTEST_ADMIN_PASSWORD    管理员账号

环境变量覆盖的意义:同一套用例既可在本地跑,也可指向 CI/测试环境,
无需修改任何代码与 YAML。
"""
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, Field, SecretStr, field_validator

from utils.yaml_utils import load_yaml

SETTINGS_FILE = Path(__file__).resolve().parent / "settings.yaml"


def _env(name: str, default: Any) -> Any:
    """读取环境变量,未设置时返回默认值;数字类型做安全转换。"""
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    if isinstance(default, bool):
        normalized = value.lower()
        if normalized in ("1", "true", "yes", "on"):
            return True
        if normalized in ("0", "false", "no", "off"):
            return False
        return value
    if isinstance(default, int):
        try:
            return int(value)
        except ValueError:
            return value
    if isinstance(default, float):
        try:
            return float(value)
        except ValueError:
            return value
    return value


class GatewaySettings(BaseModel):
    """网关配置(所有请求统一走网关,401/403 由网关 Sa-Token 产生)。"""

    base_url: str = "http://localhost:8201"
    timeout: float = Field(default=15, gt=0)
    retry: int = Field(default=1, ge=0)

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("base_url 必须是完整的 http/https URL")
        return value.rstrip("/")


class ServiceNames(BaseModel):
    """各微服务在网关上的路由前缀(StripPrefix=1 后到达真实服务)。"""

    auth: str = "mall-auth"
    admin: str = "mall-admin"
    portal: str = "mall-portal"
    search: str = "mall-search"


class Account(BaseModel):
    """一组登录账号。"""

    username: str
    password: str


class Accounts(BaseModel):
    """测试账号集合,与本地 mall 库初始化数据保持一致。"""

    member: Account
    admin: Account


class PaginationSettings(BaseModel):
    """分页默认值。"""

    default_page_size: int = 5


class EsSettings(BaseModel):
    """ES 搜索用例相关配置。"""

    keyword: str = "小米"
    min_expected_hits: int = Field(default=1, ge=0)


class DatabaseSettings(BaseModel):
    """可选 SQLAlchemy/MySQL 校验配置；默认关闭，不影响纯接口测试。"""

    enabled: bool = False
    host: str = "localhost"
    port: int = Field(default=3306, gt=0, le=65535)
    user: str = "root"
    password: SecretStr = SecretStr("")
    database: str = "mall"
    charset: str = "utf8mb4"
    connect_timeout: int = Field(default=5, gt=0)
    pool_recycle: int = Field(default=1800, gt=0)


class Settings(BaseModel):
    """框架总配置。"""

    env: str = "local"
    gateway: GatewaySettings = Field(default_factory=GatewaySettings)
    services: ServiceNames = Field(default_factory=ServiceNames)
    accounts: Accounts
    pagination: PaginationSettings = Field(default_factory=PaginationSettings)
    es: EsSettings = Field(default_factory=EsSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)

    # ------------------------------------------------------------------
    # 便捷方法:拼接各服务经网关的完整路径
    # ------------------------------------------------------------------
    def _service_path(self, service: str, path: str) -> str:
        path = path if path.startswith("/") else f"/{path}"
        return f"/{service}{path}"

    def portal(self, path: str) -> str:
        """mall-portal 服务路径,如 settings.portal('/sso/login')。"""
        return self._service_path(self.services.portal, path)

    def search(self, path: str) -> str:
        """mall-search 服务路径。"""
        return self._service_path(self.services.search, path)

    def admin(self, path: str) -> str:
        """mall-admin 服务路径。"""
        return self._service_path(self.services.admin, path)

    def auth(self, path: str) -> str:
        """mall-auth 统一认证服务路径。"""
        return self._service_path(self.services.auth, path)


def load_settings(path: Path | str | None = None) -> Settings:
    """加载配置:YAML 文件 -> 环境变量覆盖 -> Pydantic 校验。

    Pydantic 在这里的职责:启动时即完成类型/结构校验,配置错误立即暴露,
    而不是在执行到一半时才出现 KeyError/TypeError。
    """
    raw = load_yaml(path or SETTINGS_FILE)

    raw.setdefault("gateway", {})
    raw["gateway"]["base_url"] = _env("PYTEST_BASE_URL", raw["gateway"].get("base_url"))
    raw["gateway"]["timeout"] = _env("PYTEST_TIMEOUT", raw["gateway"].get("timeout"))
    raw["gateway"]["retry"] = _env("PYTEST_RETRY", raw["gateway"].get("retry"))

    accounts = raw.setdefault("accounts", {})
    member = accounts.setdefault("member", {})
    member["username"] = _env("PYTEST_MEMBER_USERNAME", member.get("username"))
    member["password"] = _env("PYTEST_MEMBER_PASSWORD", member.get("password"))
    admin = accounts.setdefault("admin", {})
    admin["username"] = _env("PYTEST_ADMIN_USERNAME", admin.get("username"))
    admin["password"] = _env("PYTEST_ADMIN_PASSWORD", admin.get("password"))

    database = raw.setdefault("database", {})
    database["enabled"] = _env("PYTEST_DB_ENABLED", database.get("enabled", False))
    database["host"] = _env("PYTEST_DB_HOST", database.get("host", "localhost"))
    database["port"] = _env("PYTEST_DB_PORT", database.get("port", 3306))
    database["user"] = _env("PYTEST_DB_USER", database.get("user", "root"))
    database["password"] = _env("PYTEST_DB_PASSWORD", database.get("password", ""))
    database["database"] = _env("PYTEST_DB_NAME", database.get("database", "mall"))

    return Settings.model_validate(raw)
