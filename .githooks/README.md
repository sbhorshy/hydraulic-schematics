# 推送前钩子

`pre-push` 在推送前运行 skill 库结构校验 `check_library.py`，库结构不过即拒绝推送。
行为与此前只存在于单机 `.git/hooks` 里的钩子等价；找不到 Python 时同样拒绝推送，不会静默放行。

## 安装（每个克隆做一次）

```bash
git config core.hooksPath .githooks
```

之后 `git push` 会自动触发。确需越过时用 `git push --no-verify`，须在 PR 中披露。

若本机 `.git/hooks/pre-push` 里已有旧钩子，设置 `core.hooksPath` 后旧钩子不再生效，无需另行删除。

## CI

`.github/workflows/library-check.yml` 在推送和拉取请求上运行同一条 `check_library.py`，作为远端兜底。

## 为什么不跑 `check_symbol.py --all`

`check_symbol.py --all` 的全量扫描当前有已知 ERROR（见 #31），纳入钩子或 CI 会让所有推送变红。
该扫描仍由手动或后续票单独接入；#31 完成后再把它加进来。这里不用跳过、白名单或降级为 WARN 的方式掩盖它。
