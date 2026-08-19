# -*- coding: utf-8 -*-
"""SQLAlchemy MySQL 查询客户端，用于接口返回与数据库结果双重校验。"""
import re
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.engine import URL, Engine

from config.settings import DatabaseSettings

_READ_ONLY_SQL = re.compile(r"^\s*(SELECT|SHOW|DESCRIBE|DESC|EXPLAIN)\b", re.IGNORECASE)


class MysqlClient:
    def __init__(self, settings: DatabaseSettings):
        self.settings = settings
        self._engine: Engine | None = None

    def _get_engine(self) -> Engine:
        if self._engine is None:
            url = URL.create(
                "mysql+pymysql",
                username=self.settings.user,
                password=self.settings.password.get_secret_value(),
                host=self.settings.host,
                port=self.settings.port,
                database=self.settings.database,
                query={"charset": self.settings.charset},
            )
            self._engine = create_engine(
                url,
                pool_pre_ping=True,
                pool_recycle=self.settings.pool_recycle,
                connect_args={"connect_timeout": self.settings.connect_timeout},
            )
        return self._engine

    @staticmethod
    def _validate_read_only(sql: str) -> None:
        normalized = sql.strip()
        # 只允许单条只读语句；拒绝注释、分号拼接和 MySQL 多语句注入。
        if (not _READ_ONLY_SQL.match(normalized)
                or "--" in normalized
                or "/*" in normalized
                or "*/" in normalized
                or ";" in normalized.rstrip(";")):
            raise ValueError("数据库断言只允许 SELECT/SHOW/DESCRIBE/EXPLAIN 查询")

    def query_all(self, sql: str, params: Any = None) -> list[dict[str, Any]]:
        self._validate_read_only(sql)
        driver_params = tuple(params) if isinstance(params, list) else (params or ())
        with self._get_engine().connect() as connection:
            result = connection.exec_driver_sql(sql, driver_params)
            return [dict(row) for row in result.mappings()]

    def query_one(self, sql: str, params: Any = None) -> dict[str, Any] | None:
        rows = self.query_all(sql, params)
        return rows[0] if rows else None

    def scalar(self, sql: str, params: Any = None) -> Any:
        row = self.query_one(sql, params)
        return next(iter(row.values())) if row else None

    def close(self) -> None:
        if self._engine is not None:
            self._engine.dispose()
            self._engine = None

    def __enter__(self) -> "MysqlClient":
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self.close()
