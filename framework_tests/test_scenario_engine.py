import subprocess
import sys
from pathlib import Path

import pytest
import requests
from pydantic import ValidationError

from config.settings import DatabaseSettings, GatewaySettings
from engine import ScenarioRunner, load_cases
from engine.assertions import AssertionEngine
from engine.models import AssertionSpec, CaseFile
from engine.template import render
from scripts.run_yaml import _parse_value
from utils.allure_utils import redact, redact_url
from utils.assertions import assert_failed
from utils.db_client import MysqlClient
from utils.http_client import ApiClient

CASES = Path(__file__).parent / "cases" / "mock_business_flow.yaml"

pytestmark = pytest.mark.framework


def test_mock_business_flow(mock_base_url):
    case = load_cases(CASES)[0]
    with ApiClient(mock_base_url, retry=0) as client:
        result = ScenarioRunner(client).run(case)

    assert len(result.responses) == 4
    assert result.context["order_id"] > 1000
    assert result.context["tracking_no"] == f"MOCK{result.context['order_id']}"


def test_template_preserves_type_and_supports_dynamic_values():
    context = {"count": 3, "name": "mall"}
    assert render("${count}", context) == 3
    assert render("project-${name}", context) == "project-mall"
    assert isinstance(render("${{timestamp}}", context), int)
    assert 1 <= render("${{random_int:1,3}}", context) <= 3


def test_report_redacts_credentials_and_tokens():
    url = "http://localhost/login?username=demo&password=123456&authCode=9999"
    assert "123456" not in redact_url(url)
    assert "9999" not in redact_url(url)
    body = redact({"data": {"token": "secret-token"}, "password": "secret-password"})
    assert body["data"]["token"] == "***"
    assert body["password"] == "***"


def test_database_assertion_compares_api_and_query_result():
    class FakeDb:
        def scalar(self, sql, params):
            assert sql == "select status from orders where id=%s"
            assert params == [1001]
            return "PAID"

    response = type("Response", (), {"status_code": 200, "text": "", "headers": {}})()
    spec = AssertionSpec(
        actual="$.data.status",
        comparator="db_eq",
        sql="select status from orders where id=%s",
        params=["${order_id}"],
    )
    AssertionEngine(FakeDb()).assert_spec(
        spec, response, {"data": {"status": "PAID"}}, {"order_id": 1001}
    )


def test_database_client_uses_sqlalchemy_pool_and_positional_params(monkeypatch):
    calls = {}

    class FakeResult:
        def mappings(self):
            return iter([{"username": "test"}])

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, *exc_info):
            return None

        def exec_driver_sql(self, sql, params):
            calls["query"] = (sql, params)
            return FakeResult()

    class FakeEngine:
        def connect(self):
            return FakeConnection()

        def dispose(self):
            calls["disposed"] = True

    def fake_create_engine(url, **kwargs):
        calls["url"] = url
        calls["options"] = kwargs
        return FakeEngine()

    monkeypatch.setattr("utils.db_client.create_engine", fake_create_engine)
    settings = DatabaseSettings(user="tester", password="secret", pool_recycle=60)
    client = MysqlClient(settings)

    assert client.scalar("SELECT username FROM ums_member WHERE id=%s", [1]) == "test"
    assert calls["query"][1] == (1,)
    assert calls["url"].drivername == "mysql+pymysql"
    assert "secret" not in str(calls["url"])
    assert calls["options"]["pool_pre_ping"] is True
    assert calls["options"]["pool_recycle"] == 60
    client.close()
    assert calls["disposed"] is True


def test_database_client_rejects_write_sql():
    client = MysqlClient(DatabaseSettings())
    with pytest.raises(ValueError, match="只允许"):
        client.query_all("DELETE FROM ums_member")


@pytest.mark.parametrize("sql", [
    "SELECT 1; DELETE FROM ums_member",
    "SELECT 1 -- hide write statement",
    "SELECT 1 /* comment */",
])
def test_database_client_rejects_unsafe_read_sql(sql):
    client = MysqlClient(DatabaseSettings())
    with pytest.raises(ValueError, match="只允许"):
        client.query_all(sql)


def test_yaml_cli_can_run_directly_from_repository_root():
    project_root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "scripts/run_yaml.py", "--help"],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "--var" in result.stdout
    assert _parse_value("12") == 12
    assert _parse_value("1.5") == 1.5
    assert _parse_value("mall") == "mall"


def test_post_timeout_is_not_retried(monkeypatch):
    client = ApiClient("http://localhost", retry=3)
    calls = 0

    def timeout(*args, **kwargs):
        nonlocal calls
        calls += 1
        raise requests.exceptions.Timeout("read timeout")

    monkeypatch.setattr(client.session, "request", timeout)
    with pytest.raises(requests.exceptions.Timeout):
        client.post("/orders", json={"productId": 1})
    assert calls == 1


def test_invalid_failure_response_cannot_pass(monkeypatch):
    response = type("Response", (), {
        "status_code": 200,
        "text": "<html>proxy error</html>",
        "json": lambda self: (_ for _ in ()).throw(ValueError()),
        "request": type("Request", (), {"method": "GET", "url": "http://localhost"})(),
    })()
    monkeypatch.setattr("utils.assertions.attach_response", lambda response: None)
    with pytest.raises(AssertionError, match="缺少 code"):
        assert_failed(response)


@pytest.mark.parametrize("values", [
    {"base_url": "not-a-url"},
    {"timeout": 0},
    {"retry": -1},
])
def test_gateway_settings_reject_invalid_values(values):
    with pytest.raises(ValidationError):
        GatewaySettings(**values)


@pytest.mark.parametrize("case_file", [
    {"cases": [{"name": "bad", "steps": [{
        "name": "typo", "request": {"method": "GET", "path": "/health"},
        "assertons": [],
    }]}]},
    {"cases": [{"name": "bad", "steps": [{
        "name": "method", "request": {"method": "TRACE", "path": "/health"},
    }]}]},
    {"cases": [{"name": "bad", "steps": [{
        "name": "path", "request": {"method": "GET", "path": "health"},
    }]}]},
])
def test_yaml_schema_rejects_typos_and_invalid_requests(case_file):
    with pytest.raises(ValidationError):
        CaseFile.model_validate(case_file)
