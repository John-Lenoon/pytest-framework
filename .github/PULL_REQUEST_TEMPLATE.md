## 变更说明

说明修改的功能和原因。

## 验证

- [ ] `python -m pytest framework_tests -m framework`
- [ ] `python -m pytest tests --collect-only -q`
- [ ] `ruff check .`
- [ ] 涉及真实 API 时，已注明测试环境和 marker
- [ ] 未提交密码、token、数据库凭据或测试报告产物

## 数据清理

说明新增用例产生的数据以及对应清理策略；不产生数据时填写“不适用”。
