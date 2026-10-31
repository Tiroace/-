# 前端提交前 pytest 关卡：发现 5 条可复现失败（非前端问题）

日期：2026-10-31 21:5x　记录人：前端开发者（执行 Chief 要求的「提交前跑 `scripts\run_pytest.ps1`」）

## 一、环境结论（已澄清）

本机 PATH 里的 `python` 是 `D:\KiCad\bin\python.exe`，确实没有 pytest。
Chief 提供的 `scripts\run_pytest.ps1` **可用**，走 DSH 自带 Python，pytest 正常执行。
之前「本机没有 pytest」的说法不准确，以本条为准。

## 二、跑了什么、结果

```
.\scripts\run_pytest.ps1
→ 5 failed, 312 passed, 15 skipped, 1 xpassed, 1304 warnings in 384.94s
exit code: 1
```

失败全部集中在 `tests/backend/test_r03_r04_retention.py`：

1. `test_过期截图被删文件删记录并写日志`
2. `test_文件已不在时仍删记录但标注出来`
3. `test_删除失败时保留记录等下轮重试`
4. `test_过期报告也会被删`
5. `test_日志按天轮转并保留180天`

断言失败形态一致：

```
assert stats["scanned"] == 1     # 实际 0
assert stats["file_missing"] == 1  # 实际 0
assert stats["file_error"] == 1    # 实际 0
assert log_path.is_file()          # False
```

即：`purge_expired_uploads()` 扫不到任何数据，删除日志也没落盘。

## 三、已定位：这是可复现的跨测试文件状态污染，不是代码缺陷

| 执行方式 | 结果 |
| --- | --- |
| `pytest tests/backend/test_r03_r04_retention.py` | **6 passed** |
| `pytest tests/backend` | 5 failed |
| `pytest tests/backend/test_a7_4_report_isolation.py + retention` | 11 passed |
| `pytest tests/backend/test_api_contract.py + retention` | **4 failed** |
| `pytest tests/backend/test_new_contracts.py + retention` | **4 failed** |
| `pytest tests/backend/test_security.py + retention` | **4 failed** |

**最小复现**（一条命令即可重现）：

```powershell
& "C:\Users\Administrator\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe" `
  -m pytest tests/backend/test_api_contract.py `
           "tests/backend/test_r03_r04_retention.py::test_过期截图被删文件删记录并写日志" -q
# → 1 failed, 39 passed
```

单独跑该用例：`1 passed`。

`test_api_contract.py` / `test_new_contracts.py` / `test_security.py` 中**任意一个**先跑，
都会让 retention 用例失败。

## 四、初步判断的成因（供负责人参考，未修改任何代码）

`backend/app/retention.py:52` 用 `get_db()` 取的是 **模块级全局连接** `deps._db`；
`test_r03_r04_retention.py` 的 `temp_db` fixture 虽然会 `monkeypatch.setattr("backend.app.deps.get_settings", ...)`
并重置 `deps._db = None`，但如果前面某个测试文件把 `get_db` 的引用或 `deps._db` 留在了
另一个方向（例如 cache 了旧的 settings / 旧连接），`temp_db` 里的 `get_db(settings)` 就与
`retention.get_db()` 拿到的不是同一个对象，于是扫描到的是另一张空库。

这不是断言写错，也不是引擎/前端问题；**是测试之间共享全局单例没有隔离**。

## 五、影响与建议

- **影响范围**：只影响 `pytest tests` 全量跑的绿/红判定，不影响线上代码路径。
- **建议归属**：后端/测试负责人（`tests/backend/` 与 `backend/app/deps.py` 属其范围）。
- **可能的修法**（三选一，需负责人定）：
  1. 在 `tests/backend/conftest.py` 加一个 autouse fixture，每个测试前后都 `deps._db = None`；
  2. `get_db()` 改为每次按当前 `get_settings()` 取，不用模块级 cache；
  3. retention fixture 改为直接注入 db，绕开全局单例。
- **在修好之前**：前端提交前跑 `run_pytest.ps1` 会看到 5 红，**这 5 条与前端改动无关**，
  前端四套自检（check:r1 / test / check:report / check:r3）+ 构建后检查不受影响。

## 六、前端本次提交前实际执行过的关卡

| 关卡 | 结果 |
| --- | --- |
| `src` 下 `npm run check:r1` | 52/52 |
| `src` 下 `npm test` | 47/47 |
| `src` 下 `npm run check:report` | 33/33 |
| `src` 下 `npm run check:r3` | 38/38 |
| `npm run build:mp-weixin` 构建后检查 | 15/15 |
| `python -m engine.selftest` | 76/76 |
| `scripts\run_pytest.ps1` | 5 failed（上述污染，非前端） |
