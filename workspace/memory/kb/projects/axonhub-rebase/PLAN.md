# AxonHub Rebase 计划：branch-1 安全修复合入上游 unstable

> 生成时间：2026-04-29
> 仓库：hdot123/axonhub (fork) ← looplj/axonhub (upstream)
> 状态：待执行

---

## 1. 背景与目标

### 当前分支状态

| 分支 | 基线 | commit 数 | 内容 |
|------|------|-----------|------|
| `origin/branch-1`（我们的主线） | `65eb7783`（旧上游 HEAD） | 38 commits | 100 项 F-D 安全修复 + 百炼兼容 |
| `upstream/unstable`（最新上游） | `9acca6be`（新上游 HEAD） | 14 commits 新增 | 新功能：channel limiter、provider quota enforcement、custom endpoints、auto reasoning effort 等 |

### 目标

将我们的 100 项安全修复迁移到最新上游代码之上，确保：

1. 所有安全修复逻辑不丢失
2. 上游新功能完整保留
3. 全部测试通过（`go test ./...`）
4. GraphQL 生成代码通过 `go generate` 重新生成

---

## 2. 冲突分析

### 总览

- 我们的变更涉及 **164 个文件**（相对基线）
- 上游变更涉及 **308 个文件**（相对基线）
- **重叠文件 41 个**，分三档：

### 2.1 重度冲突（4 个文件）

| 文件 | 上游变更行数 | 我们变更行数 | 冲突原因 | 解决策略 |
|------|-------------|-------------|----------|----------|
| `internal/server/gql/generated.go` | 2064 | 161 | GraphQL 生成代码，上游新增大量 resolver | 以上游为准，W5 重放 resolver 逻辑，W6 `go generate` 重新生成 |
| `internal/server/orchestrator/lb_strategy_rate_limit.go` | 406 | 55 | 上游重构了整个 rate limit 策略 | 以上游新结构为准，我们的 F-D 修复在新结构上重新实现 |
| `internal/server/biz/system.go` | 146 | 278 | 双端都大幅修改 | 逐函数比对，保留我们的安全修复 + 上游新功能 |
| `internal/ent/mutation.go` | 169 | 77 | Ent 生成代码 | 以上游为准，W6 `go generate` 重新生成 |

### 2.2 中度冲突（8 个文件）

| 文件 | 上游 | 我们 | 解决策略 |
|------|------|------|----------|
| `internal/server/biz/provider_quota.go` | 399 | 10 | 上游大幅扩展，我们的改动小，合入即可 |
| `internal/server/orchestrator/connection_tracking.go` | 235 | 17 | 上游重构了整块，F-D56/57 修复需在新结构上重新实现 |
| `internal/server/gql/dashboard.resolvers.go` | 74 | 177 | 我们改的多（F-D82/83/84/87），需重放到上游新版本 |
| `internal/server/db/ent.go` | 130 | 14 | 上游新增读写分离，我们的 S3 atomic 修复合入 |
| `llm/httpclient/client.go` | 4 | 84 | 我们改的多（F-D75/76/77），上游改的少，直接 cherry-pick |
| `internal/server/orchestrator/lb_strategy_bp_test.go` | 156 | 18 | **上游已删除 `lb_strategy_bp.go`**，此测试文件作废，跳过 |
| `internal/ent/gql_where_input.go` | 64 | 64 | Ent 生成代码，`go generate` 解决 |
| `internal/server/biz/api_key.go` | 6 | 60 | 我们改的多（F-D52/85/86），上游改的少 |

### 2.3 轻度冲突（29 个文件）

双端都小改，容易合并。完整列表：

```
internal/ent/entql.go
internal/ent/gql_collection.go
internal/ent/gql_node_descriptor.go
internal/ent/internal/schema.go
internal/ent/migrate/schema.go
internal/ent/runtime/runtime.go
internal/server/biz/provider_quota/claudecode_checker.go
internal/server/biz/request.go
internal/server/gql/axonhub.resolvers.go
internal/server/gql/ent.graphql
internal/server/gql/graphql.go
internal/server/gql/system.resolvers.go
internal/server/orchestrator/candidates_basic_test.go
internal/server/orchestrator/candidates_decorator_test.go
internal/server/orchestrator/candidates_loadbalance_test.go
internal/server/orchestrator/channel_help_test.go
internal/server/orchestrator/load_balancer.go
internal/server/orchestrator/orchestrator.go
internal/server/orchestrator/outbound.go
llm/httpclient/model.go
llm/oauth/device_flow_provider.go
llm/oauth/token_provider.go
llm/pipeline/pipeline.go
llm/streams/prepend.go
llm/transformer/anthropic/outbound_stream.go
llm/transformer/gemini/outbound.go
llm/transformer/openai/aggregator.go
llm/transformer/openai/model.go
llm/transformer/openai/outbound_convert.go
```

### 2.4 无冲突文件

- 上游新增 267 个文件，我们没碰过 → 直接带过来
- 我们新增约 150 个文件（安全修复 + 测试 + CI），上游没碰过 → 直接带过来

---

## 3. 我们的 38 个 Commit 清单

按时间顺序（新→旧）：

```
b0c3fedd test(bailian): add sanitizeForBailian unit tests
9b1652ab fix(bailian): strip response_format and ensure tool arguments are valid JSON
6ec9a3e2 merge: branch-2 -> branch-1（空 merge commit，跳过）
a7c3e2d6 fix: CI 阻塞项修复 — go.mod tidy + workflow branch-2 触发 + GOTOOLCHAIN: auto
04ae3386 fix: usage_cost_test + usage_log_test signature
5dc4ea19 fix: remaining biz system/thread/trace test signature
aec02c96 fix: system_onboarding_test := to =
54508261 fix(f11): live_streaming_test.go — sync.Once field adaptation
d2d2596b fix(f7): orchestrator tests — 2-value signature adaptation
0860f682 fix(f6): middleware/migrator/api test — 2-value signature adaptation
9a4e0d2e fix(f3): F-D98 — Initialize sync.Once anti-reentry
63a0f34a fix(f4): data_storage_test.go — signature + *string adaptation
5d3e5ed0 fix(f8): dataurl_test.go — text/html → text/plain whitelist compat
8daa206a fix(f2): F-D24 — livePreviewMiddleware sync.Once
5897f62d fix(f5): gc_test.go — signature + CleanupStats adaptation
faadd74d fix(r8): F-D33/F-D35/F-D38 — S3 atomic + DB/GCS ctx propagation
2e452eec fix(r10): F-D74/50/45/46/47 — builder panic + GraphQL N+1/Nodes/scope
056763f9 fix(r9): F-D37/F-D29 — Dumper cleanup logic + wrapHttpError sanitization
d22f1800 fix(r6): F-D8/F-D9/F-D10 — retry ctx + backoff + body limit
f2e210f7 fix(r4): F-D25/F-D26/F-D27 — backup failure path + full data + prefix match
f16bcedf fix(r5): F-D7/F-D34/F-D72 — GC retry + WaitGroup + soft-delete respect
d9bcd93f fix(r3): F-D19/F-D22 — sliding window + half-open circuit breaker
0a3c8cc8 fix(r1): F-D2 — AllowNoAuth empty-key passthrough fix
2e91ddcb fix(w8b): F-D44/78/79 — Anthropic fallback + content-type + URL parsing
06c895d2 fix(w8c): F-D80/81 — Gemini URL dedup + Anthropic Moonshot heuristic
951f32c2 fix(c6): F-D85/F-D86 — Redis panic + provider_quota syntax
d6ddde95 fix(w8a): F-D39/40/41/42/43 — Transformer nil/subtraction/overwrite fixes
3450f698 fix(c3): F-D56/F-D57 — connection tracking + perf race fix
5852a204 fix(c6): F-D88/F-D89/F-D90 — closed atomic + watcher ctx + tracker read reset
df84c9e0 fix(w9a): F-D52/60/63/64/65 — security hardening batch 1
ac3bb7ff fix(c7): F-D58/F-D61/F-D62/F-D91/F-D92/F-D93 — backup/GC P3 fixes
35e33718 fix(c4): F-D49/F-D59/F-D68/F-D70 — middleware/migration/aggregation fixes
9431022f fix(c8): F-D71/F-D72/F-D73/F-D94/F-D95/F-D96/F-D97 — migration/misc P3 fixes
e2393c94 fix(w10): F-D82/83/84/87 — GraphQL/misc P3 fixes
165c9ffe fix(c5): F-D74(verify)/F-D75/F-D76/F-D77 — HTTP client P2 fixes
df7d9002 fix(worker-c2): Redis/cache deepening — F-D21/F-D51/F-D53/F-D54/F-D55
44c33ef7 fix(phase1): F-D2+F-D3 NoAuth + F-D1 FlushAll + F-D28+F-D29+F-D30 凭证泄露 + F-D15+F-D16+F-D17 Transformer
abe1157f fix(phase1): F-D4+F-D5+F-D13 HTTP超时 + F-D6 Close错误传播 + F-D18 分页校验 + F-D100 Redis连接池 + F-D101 SQLite WAL
```

---

## 4. 执行计划：6 个 Worker 并行

### 前置条件

```bash
cd /Users/busiji/tool/axonhub
git fetch upstream
git checkout -b branch-2 upstream/unstable   # 从最新上游创建任务分支
```

### Worker 分工表

每个 Worker 的写集（文件范围）互不重叠，可以并行执行。

---

### W1: ent 层（生成代码 + schema + migration）

**职责：** 处理所有 `internal/ent/` 下的冲突和变更

**分配 commit（按顺序 cherry-pick）：**
1. `951f32c2` — fix(c6): F-D85/F-D86 — Redis panic + provider_quota syntax（ent 部分）
2. `e2393c94` — fix(w10): F-D82/83/84/87（ent.graphql 部分）

**涉及文件：**
```
internal/ent/apikey.go
internal/ent/apikey/apikey.go
internal/ent/apikey/where.go
internal/ent/apikey_create.go
internal/ent/apikey_update.go
internal/ent/ent.graphql
internal/ent/entql.go
internal/ent/gql_collection.go
internal/ent/gql_node_descriptor.go
internal/ent/gql_where_input.go
internal/ent/internal/schema.go
internal/ent/migrate/datamigrate/migrator.go
internal/ent/migrate/datamigrate/v0.3.0.go
internal/ent/migrate/schema.go
internal/ent/mutation.go
internal/ent/runtime/runtime.go
```

**冲突解决规则：**
- `mutation.go`、`gql_where_input.go`、`entql.go`、`gql_collection.go`、`gql_node_descriptor.go`、`runtime.go`、`internal/schema.go`、`migrate/schema.go`：这些是 Ent 生成代码或 schema 文件，**以上游为准**，我们的修复如果涉及 schema 变更（如 apikey 新字段），需要在新的上游 schema 上重新添加
- `ent.graphql`：以上游为准，我们的 GraphQL 限制逻辑在 W5 的 resolver 层处理
- `apikey*.go`：如果上游也改了 apikey schema，需要合并字段定义

**验证：**
```bash
go vet ./internal/ent/...
```

**不执行 `go generate`**（留给 W6 统一做）

---

### W2: orchestrator 层（调度器 + 负载均衡 + 连接追踪）

**职责：** 处理所有 `internal/server/orchestrator/` 下的冲突和变更

**分配 commit（按顺序 cherry-pick）：**
1. `3450f698` — fix(c3): F-D56/F-D57 — connection tracking + perf race fix
2. `d9bcd93f` — fix(r3): F-D19/F-D22 — sliding window + half-open circuit breaker
3. `df7d9002` — fix(worker-c2): 部分（lb_strategy_rate_limit.go, load_balancer.go）
4. `e2393c94` — fix(w10): 部分（pass_through.go）
5. `165c9ffe` — fix(c5): 部分（streams/prepend.go 之外的部分）
6. `8daa206a` — fix(f2): F-D24 — livePreviewMiddleware sync.Once
7. `d2d2596b` — fix(f7): orchestrator tests — 2-value signature adaptation
8. `54508261` — fix(f11): live_streaming_test.go — sync.Once field adaptation

**涉及文件：**
```
internal/server/orchestrator/connection_tracking.go
internal/server/orchestrator/performance.go
internal/server/orchestrator/channel_request_tracker.go
internal/server/orchestrator/lb_strategy_rate_limit.go
internal/server/orchestrator/load_balancer.go
internal/server/orchestrator/pass_through.go
internal/server/orchestrator/orchestrator.go
internal/server/orchestrator/outbound.go
internal/server/orchestrator/inbound.go
internal/server/orchestrator/live_streaming.go
internal/server/orchestrator/candidates_basic_test.go
internal/server/orchestrator/candidates_decorator_test.go
internal/server/orchestrator/candidates_loadbalance_test.go
internal/server/orchestrator/channel_help_test.go
internal/server/orchestrator/lb_strategy_bp_test.go  ⚠️ 上游已删除，跳过
internal/server/orchestrator/live_streaming_test.go
internal/server/orchestrator/inbound_test.go
internal/server/orchestrator/lb_strategies_test.go
internal/server/orchestrator/lb_strategy_rr_test.go
internal/server/orchestrator/lb_strategy_trace_test.go
internal/server/orchestrator/load_balancer_test.go
internal/server/orchestrator/pass_through_test.go
internal/server/orchestrator/request_test.go
internal/server/orchestrator/candidates_cache_test.go
internal/server/orchestrator/candidates_dedup_test.go
internal/server/orchestrator/candidates_google_test.go
```

**冲突解决规则：**
- `lb_strategy_rate_limit.go`：上游重构了整块（+406/-原始），**以上游新结构为准**，我们的 F-D 修复（retry ctx + backoff）需在新代码中重新实现
- `connection_tracking.go`：上游重构了（+235/-原始），F-D56/57 的 connection tracking 修复需在新结构上重新实现
- `lb_strategy_bp_test.go`：**上游已删除对应源文件 `lb_strategy_bp.go`**，此测试文件跳过
- `orchestrator.go`：上游新增了 auto reasoning effort 等，我们的修改是防御性的，合入
- 测试文件：适配上游新的函数签名和结构

**⚠️ 关键注意事项：**
- 上游新增了 `channel_limiter.go`、`channel_limiter_manager.go`、`channel_queue_error.go` 等文件，不要修改它们
- 上游用 `lb_strategy_quota.go` 替代了 `lb_strategy_bp.go`
- 上游新增了 `candidates_quota.go`、`custom_endpoints.go`

**验证：**
```bash
go vet ./internal/server/orchestrator/...
```

---

### W3: biz 层 + backup + gc + middleware + dumper

**职责：** 处理所有 `internal/server/biz/`、`internal/server/backup/`、`internal/server/gc/`、`internal/server/middleware/`、`internal/dumper/` 下的冲突和变更

**分配 commit（按顺序 cherry-pick）：**
1. `44c33ef7` — fix(phase1): 部分（biz/api_key.go, middleware/auth.go, biz/system.go）
2. `0a3c8cc8` — fix(r1): F-D2 — AllowNoAuth empty-key passthrough fix
3. `f16bcedf` — fix(r5): F-D7/F-D34/F-D72 — GC retry + WaitGroup + soft-delete respect
4. `f2e210f7` — fix(r4): F-D25/F-D26/F-D27 — backup failure path + full data + prefix match
5. `faadd74d` — fix(r8): F-D33/F-D35/F-D38 — S3 atomic + DB/GCS ctx propagation
6. `ac3bb7ff` — fix(c7): F-D58/F-D61/F-D62/F-D91/F-D92/F-D93 — backup/GC P3 fixes
7. `35e33718` — fix(c4): F-D49/F-D59/F-D68/F-D70 — middleware/migration/aggregation fixes
8. `056763f9` — fix(r9): F-D37/F-D29 — Dumper cleanup logic + wrapHttpError sanitization
9. `9431022f` — fix(c8): 部分（data_storage.go, dataurl.go）
10. `df84c9e0` — fix(w9a): 部分（api_key.go, gc.go, middleware/recover.go, middleware/trace.go）
11. `2e452eec` — fix(r10): 部分（provider_quota/claudecode_checker.go）
12. `9a4e0d2e` — fix(f3): F-D98 — Initialize sync.Once anti-reentry
13. `df7d9002` — fix(worker-c2): 部分（biz/quota.go）

**涉及文件：**
```
internal/server/biz/api_key.go
internal/server/biz/api_key_internal.go
internal/server/biz/api_key_test.go
internal/server/biz/auth.go
internal/server/biz/auth_test.go
internal/server/biz/channel_internal.go
internal/server/biz/channel_probe_internal.go
internal/server/biz/data_storage.go
internal/server/biz/data_storage_test.go
internal/server/biz/fx_module.go
internal/server/biz/model_circuit_breaker.go
internal/server/biz/prompt.go
internal/server/biz/prompt_protection_rule.go
internal/server/biz/provider_quota.go
internal/server/biz/provider_quota/claudecode_checker.go
internal/server/biz/provider_quota_internal.go
internal/server/biz/quota.go
internal/server/biz/request.go
internal/server/biz/request_internal.go
internal/server/biz/system.go
internal/server/biz/system_onboarding.go
internal/server/biz/system_proxy.go
internal/server/biz/webhook_notifier.go
internal/server/backup/autobackup.go
internal/server/backup/autobackup_internal.go
internal/server/backup/backup_ops.go
internal/server/backup/restore.go
internal/server/backup/service.go
internal/server/backup/types.go
internal/server/gc/gc.go
internal/server/gc/gc_internal.go
internal/server/gc/gc_test.go
internal/server/middleware/auth.go
internal/server/middleware/project.go
internal/server/middleware/recover.go
internal/server/middleware/thread.go
internal/server/middleware/trace.go
internal/server/middleware/thread_test.go
internal/server/middleware/trace_test.go
internal/server/dependencies/fx_module.go
internal/server/db/ent.go
internal/dumper/dumper.go
internal/server/video_storage/worker.go
```

**冲突解决规则：**
- `system.go`：重度冲突（上游+146/我们+278），**逐函数比对**：上游新增的 provider quota / channel limiter 配置保留，我们的安全修复（JWT 吊销、分页校验、sync.Once）保留
- `provider_quota.go`：上游+399 行扩展，我们只+10 行，直接 cherry-pick 即可
- `db/ent.go`：上游新增读写分离（+130），我们的 S3 atomic 修复（+14）合入
- `claudecode_checker.go`：双端都改了，合并逻辑
- `auth.go` / `middleware/auth.go`：我们的 JWT 吊销和 NoAuth 修复保留

**验证：**
```bash
go vet ./internal/server/biz/...
go vet ./internal/server/backup/...
go vet ./internal/server/gc/...
go vet ./internal/server/middleware/...
go vet ./internal/dumper/...
```

---

### W4: llm 层（pipeline + httpclient + transformer + oauth）

**职责：** 处理所有 `llm/` 下的冲突和变更

**分配 commit（按顺序 cherry-pick）：**
1. `abe1157f` — fix(phase1): F-D4/5/6/13/18/100/101（httpclient, pipeline 部分）
2. `44c33ef7` — fix(phase1): 部分（httpclient/model.go, oauth/token_provider.go, transformer 部分）
3. `d22f1800` — fix(r6): F-D8/F-D9/F-D10 — retry ctx + backoff + body limit
4. `d6ddde95` — fix(w8a): F-D39/40/41/42/43 — Transformer nil/subtraction/overwrite fixes
5. `2e91ddcb` — fix(w8b): F-D44/78/79 — Anthropic fallback + content-type + URL parsing
6. `06c895d2` — fix(w8c): F-D80/81 — Gemini URL dedup + Anthropic Moonshot heuristic
7. `165c9ffe` — fix(c5): 部分（pipeline.go, prepend.go）
8. `9431022f` — fix(c8): 部分（httpclient/utils.go, oauth/device_flow_provider.go）

**涉及文件：**
```
llm/go.mod
llm/go.sum
llm/httpclient/builder.go
llm/httpclient/client.go
llm/httpclient/client_test.go
llm/httpclient/decoder.go
llm/httpclient/model.go
llm/httpclient/utils.go
llm/oauth/device_flow_provider.go
llm/oauth/token_provider.go
llm/pipeline/pipeline.go
llm/streams/prepend.go
llm/transformer/anthropic/aggregator.go
llm/transformer/anthropic/outbound_stream.go
llm/transformer/anthropic/usage.go
llm/transformer/anthropic/usage_test.go
llm/transformer/anthropic/testdata/llm-stop.stream.jsonl
llm/transformer/anthropic/testdata/llm-think.stream.jsonl
llm/transformer/anthropic/testdata/llm-tool.stream.jsonl
llm/transformer/gemini/convert.go
llm/transformer/gemini/inbound.go
llm/transformer/gemini/outbound.go
llm/transformer/gemini/outbound_test.go
llm/transformer/openai/aggregator.go
llm/transformer/openai/inbound.go
llm/transformer/openai/inbound_convert.go
llm/transformer/openai/model.go
llm/transformer/openai/outbound_convert.go
llm/transformer/openai/responses/usage.go
llm/transformer/aisdk/convert_request.go
llm/transformer/aisdk/convert_request_test.go
```

**冲突解决规则：**
- `client.go`：我们+84 行（F-D75/76/77 HTTP client 修复），上游只+4 行，直接 cherry-pick
- `pipeline.go`：双端都小改，合并即可
- `oauth/token_provider.go`：我们+50 行（凭证泄露防护），上游+7 行，合入
- `transformer/*`：上游做了 reformat（`chore: reformat llm package`），如果冲突是纯格式差异，以上游格式为准

**⚠️ 重要：llm 是独立 Go module**
```bash
# 所有 go 命令必须在 llm/ 目录下执行
cd llm && go build ./...
cd llm && go vet ./...
cd llm && go test ./...
```

**验证：**
```bash
cd /Users/busiji/tool/axonhub/llm && go vet ./...
```

---

### W5: gql resolver 层 + CI workflow

**职责：** 处理所有 `internal/server/gql/` 和 `.github/workflows/` 下的冲突和变更

**分配 commit（按顺序 cherry-pick）：**
1. `951f32c2` — fix(c6): 部分（dashboard.resolvers.go, outbound.go）
2. `5852a204` — fix(c6): F-D88/F-D89/F-D90（inbound.go, outbound.go）
3. `e2393c94` — fix(w10): 部分（dashboard.resolvers.go, graphql.go, system.resolvers.go）
4. `2e452eec` — fix(r10): 部分（ent.resolvers.go）
5. `a7c3e2d6` — fix: CI 阻塞项修复（workflows + go.mod）

**涉及文件：**
```
internal/server/gql/axonhub.resolvers.go
internal/server/gql/dashboard.resolvers.go
internal/server/gql/ent.graphql
internal/server/gql/ent.resolvers.go
internal/server/gql/generated.go      ⚠️ 重度冲突，不直接改，留给 W6 go generate
internal/server/gql/graphql.go
internal/server/gql/me.resolvers.go
internal/server/gql/system.resolvers.go
internal/server/gql/system.resolvers_test.go
.github/workflows/build.yml
.github/workflows/lint.yml
.github/workflows/test.yml
```

**冲突解决规则：**
- `generated.go`：**不要手动合并**，以上游版本为基础，在 resolver 文件中重放我们的修复，最终由 W6 的 `go generate` 重新生成
- `dashboard.resolvers.go`：我们+177 行（F-D82/83/84 N+1 修复），上游+74 行，需仔细合并
- `ent.graphql`、`graphql.go`：我们的 complexity limit 等配置保留
- CI workflows：我们的 branch-2 触发配置需要适配新结构

**验证：**
```bash
go vet ./internal/server/gql/...
```

---

### W6: 测试修复 + bailian + go generate + 全量验证

**职责：** 测试文件签名适配、百炼兼容、最终的代码生成和全量测试

**⚠️ 此 Worker 必须等 W1-W5 全部完成后才能开始**

**分配 commit（按顺序 cherry-pick）：**
1. `9b1652ab` — fix(bailian): strip response_format + ensure tool arguments
2. `b0c3fedd` — test(bailian): sanitizeForBailian unit tests
3. `04ae3386` — fix: usage_cost_test + usage_log_test signature
4. `5dc4ea19` — fix: remaining biz system/thread/trace test signature
5. `aec02c96` — fix: system_onboarding_test := to =
6. `63a0f34a` — fix(f4): data_storage_test.go — signature + *string adaptation
7. `5897f62d` — fix(f5): gc_test.go — signature + CleanupStats adaptation
8. `0860f682` — fix(f6): middleware/migrator/api test — 2-value signature adaptation
9. `5d3e5ed0` — fix(f8): dataurl_test.go — text/html → text/plain whitelist compat

**涉及文件（全部是测试文件或 bailian）：**
```
llm/transformer/bailian/outbound.go
llm/transformer/bailian/sanitize_test.go
internal/server/biz/usage_cost_test.go
internal/server/biz/usage_log_test.go
internal/server/biz/system_test.go
internal/server/biz/system_onboarding_test.go
internal/server/biz/thread_test.go
internal/server/biz/trace_test.go
internal/server/biz/data_storage_test.go
internal/server/gc/gc_test.go
internal/ent/migrate/datamigrate/migrator_test.go
internal/ent/migrate/datamigrate/v0.4.0_test.go
internal/server/api/openai_retrieve_test.go
internal/server/api/request_content_test.go
internal/server/api/request_live_test.go
internal/server/middleware/thread_test.go
internal/server/middleware/trace_test.go
internal/pkg/xurl/dataurl_test.go
```

**go generate 步骤（在 W1-W5 所有代码合并完成后执行）：**
```bash
cd /Users/busiji/tool/axonhub
go generate ./internal/ent/...
go generate ./internal/server/gql/...
```

**冲突解决规则：**
- 测试文件：适配上游新的函数签名（很多函数新增了返回值或参数）
- `system_onboarding_test.go`：`:=` 改 `=` 的问题可能上游已修
- bailian 文件：无冲突（上游没碰）

**验证（逐步升级）：**
```bash
# Step 1: 编译
go build ./...

# Step 2: 分模块测试
go test ./internal/ent/... -count=1 -timeout 120s
go test ./internal/server/biz/... -count=1 -timeout 120s
go test ./internal/server/orchestrator/... -count=1 -timeout 120s
go test ./internal/server/gql/... -count=1 -timeout 120s
go test ./internal/server/middleware/... -count=1 -timeout 60s
go test ./internal/server/backup/... -count=1 -timeout 60s
go test ./internal/server/gc/... -count=1 -timeout 60s
cd llm && go test ./... -count=1 -timeout 120s

# Step 3: 全量测试（最终门禁）
go test ./... -count=1 -timeout 300s

# Step 4: race detector（可选，CI 会跑）
go test -race ./... -count=1 -timeout 300s
```

---

## 5. 执行流程图

```
upstream/unstable (9acca6be)
       │
       ├── git checkout -b branch-2
       │
       ├── ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐
       │   │   W1    │  │   W2    │  │   W3    │  │   W4    │  │   W5    │
       │   │  ent层  │  │  orch   │  │ biz层   │  │  llm层  │  │  gql层  │
       │   │         │  │  层     │  │ +相关   │  │         │  │ +CI     │
       │   └────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘
       │        │            │            │            │            │
       │        └────────────┴─────┬──────┴────────────┴────────────┘
       │                          │
       │                    W1-W5 全部完成
       │                          │
       │                   ┌──────┴──────┐
       │                   │     W6      │
       │                   │ 测试修复    │
       │                   │ bailian     │
       │                   │ go generate │
       │                   │ 全量测试    │
       │                   └──────┬──────┘
       │                          │
       │                    全部测试通过
       │                          │
       ├── merge to branch-1 ─────┤
       │                          │
       ├── git push origin branch-1
       ├── git push origin --delete branch-2
       └── 完成
```

---

## 6. Worker 执行模板

每个 Worker 在开始工作前必须：

1. **读取本文档**（`REBASE-PLAN.md`）了解自己的职责范围
2. **确认 branch-2 存在且基于 `upstream/unstable`**
3. **只修改自己负责的文件**（见上方涉及文件列表）
4. **不修改其他 Worker 负责的文件**

每个 Worker 执行步骤：

```bash
# 1. 切到 branch-2
cd /Users/busiji/tool/axonhub
git checkout branch-2

# 2. cherry-pick 分配的 commit（按顺序）
git cherry-pick <commit-hash>

# 3. 遇到冲突时：
#    - 查看冲突文件：git diff --name-only --diff-filter=U
#    - 按本文档的冲突解决规则处理
#    - git add <resolved-files>
#    - git cherry-pick --continue

# 4. 验证
go vet ./对应模块/...     # W4 用 cd llm && go vet ./...

# 5. 汇报结果
```

---

## 7. 冲突解决通用原则

| 场景 | 策略 |
|------|------|
| Ent 生成代码冲突 | 以上游为准，最终 `go generate` 重新生成 |
| GraphQL 生成代码冲突 | 以上游为准，最终 `go generate` 重新生成 |
| 上游重构了模块结构 | 以上游新结构为准，我们的修复在新结构上重新实现 |
| 纯格式差异（reformat） | 以上游格式为准 |
| 我们的安全修复 vs 上游的新功能 | **两者都保留**，安全修复优先 |
| 上游已修了同一个 bug | 取上游版本，检查是否等价 |
| 测试文件签名不匹配 | 适配上游新的签名 |

---

## 8. 已知跳过项

| 项目 | 原因 |
|------|------|
| `lb_strategy_bp_test.go` | 上游已删除 `lb_strategy_bp.go`，此测试作废 |
| `merge commit 6ec9a3e2` | 空 merge，无实际代码变更 |

---

## 9. 验收标准

- [ ] `go build ./...` 零错误
- [ ] `go vet ./...` 零警告
- [ ] `go test ./... -count=1 -timeout 300s` 全绿
- [ ] `go generate ./internal/ent/... ./internal/server/gql/...` 无报错，生成代码与手动修改一致
- [ ] 所有 100 项 F-D 安全修复逻辑不丢失（逐项可追溯）
- [ ] 上游 14 个 commit 的所有新功能完整保留
- [ ] branch-2 合回 branch-1 并 push
- [ ] branch-2 删除

---

## 10. 回退方案

如果 rebase 过程中发现不可调和的冲突或上游变更导致修复不再适用：

1. `git rebase --abort` 或 `git cherry-pick --abort` 放弃当前操作
2. `git checkout branch-1` 回到安全状态
3. 在本计划文档中记录阻塞点和原因
4. 等待人工决策

---

## 11. 主线程接力协议

> **本节是任何会话的主线程都必须首先读取和遵循的协议。**
> 多会话接力时，每个会话的主线程必须按以下步骤工作，确保任务不丢失、不重复。

### 11.1 会话启动检查清单（每次新会话必须执行）

```bash
# Step 1: 拉取最新状态
cd /Users/busiji/tool/axonhub
git fetch upstream
git fetch origin

# Step 2: 读取执行状态文件
cat /Users/busiji/tool/REBASE-STATE.md

# Step 3: 读取本计划文档（特别是 Section 4 Worker 分工）
head -200 /Users/busiji/tool/REBASE-PLAN.md

# Step 4: 检查 branch-2 是否存在
git branch -a | grep branch-2

# Step 5: 如果 branch-2 不存在且 P0 未完成，先执行 P0
#         如果 branch-2 不存在且 P0 已完成，说明被意外删除，从状态文件恢复
```

### 11.2 状态文件：REBASE-STATE.md

状态文件与计划文件同目录：`/Users/busiji/tool/REBASE-STATE.md`

**这是唯一的状态源。** 看板卡片只用于人类可视化，子代理不看板。

状态文件格式如下：

```markdown
# REBASE 执行状态

> 最后更新：YYYY-MM-DD HH:MM
> 更新者：会话ID 或 描述

## 总体状态：未开始 / 进行中 / 阻塞 / 已完成

## 任务进度

| 任务 | 状态 | 分派会话 | 完成会话 | 结果摘要 |
|------|------|----------|----------|----------|
| P0: 创建 branch-2 | Todo/InProgress/Done/Blocked | | | |
| W1: ent 层 | Todo/InProgress/Done/Blocked | | | |
| W2: orchestrator 层 | Todo/InProgress/Done/Blocked | | | |
| W3: biz 层 | Todo/InProgress/Done/Blocked | | | |
| W4: llm 层 | Todo/InProgress/Done/Blocked | | | |
| W5: gql 层 + CI | Todo/InProgress/Done/Blocked | | | |
| W6: 测试 + generate + 验收 | Todo/InProgress/Done/Blocked | | | |
| P1: merge + push + 清理 | Todo/InProgress/Done/Blocked | | | |

## 阻塞记录

（如有阻塞项，记录在这里）

## 决策记录

（冲突解决中的关键决策，供后续会话参考）
```

### 11.3 主线程调度流程

```
新会话启动
    │
    ├── 读取 REBASE-STATE.md
    │
    ├── P0 未完成？
    │   ├── 是 → 执行 P0（创建 branch-2），更新状态文件，同步看板
    │   └── 否 → 继续
    │
    ├── W1-W5 有未完成的？
    │   ├── 是 → 并行分派未完成的 Worker（子代理模型：gpt-5.4-mini）
    │   │         每个 Worker 的 message 包含：
    │   │         - 它在 REBASE-PLAN.md 中的 Section 编号
    │   │         - 它的写集（文件范围）
    │   │         - 关键约束（不碰其他 Worker 的文件）
    │   │         - 验证命令
    │   │   └── 全部完成 → 继续
    │
    ├── W6 未完成？
    │   ├── 是 → 等待 W1-W5 全部 Done 后，分派 W6
    │   └── 否 → 继续
    │
    ├── P1 未完成？
    │   ├── 是 → 执行 merge + push + 清理
    │   └── 否 → 任务已全部完成
    │
    └── 每个步骤完成后：
        1. 更新 REBASE-STATE.md
        2. 同步更新 GitHub Project 看板状态
        3. git add + commit 状态变更（如果 branch-2 存在）
```

### 11.4 子代理分派模板

每个子代理的 spawn message 必须包含以下信息：

```
你是 Worker N（WN），负责 AxonHub rebase 任务的一个模块。

## 你的计划文档
读取 /Users/busiji/tool/REBASE-PLAN.md，重点看 Section 4 中你的部分（WN）。

## 你的写集
（列出允许修改的文件范围）

## 禁止
- 不要修改其他 Worker 负责的文件
- 不要执行 go generate（留给 W6）
- 不要修改 branch-1

## 工作分支
git checkout branch-2

## 工作步骤
1. 按 REBASE-PLAN.md 中你的 commit 列表，逐个 cherry-pick
2. 遇冲突按文档规则解决
3. 完成后跑验证命令
4. 汇报结果：成功 / 失败 + 冲突详情

## 你的 commit hash 列表（按顺序）
（列出分配的 commit）
```

### 11.5 状态更新规则

1. **每个状态变更都必须写入 REBASE-STATE.md**，包括时间戳
2. **看板同步是可选的**（如果 gh CLI 可用就同步，不可用也不阻塞）
3. **Worker 完成/失败后**，主线程必须：
   - 读取 Worker 的输出
   - 验证 Worker 的改动（`git diff --stat`）
   - 在 branch-2 上验证 `go build ./...`
   - 更新 REBASE-STATE.md
   - 如果失败，记录阻塞原因
4. **不要重复执行已 Done 的任务**（检查状态文件）
5. **如果某个 Worker 在上一个会话中是 InProgress 但没有完成结果**，视为未开始，重新分派

### 11.6 异常恢复

| 场景 | 处理方式 |
|------|----------|
| branch-2 不存在但 W1-W6 有 InProgress | 从 `upstream/unstable` 重新创建 branch-2，将已 Done 的 Worker 的改动通过 cherry-pick 重新应用 |
| branch-2 存在但 go build 失败 | 定位失败模块，重新分派对应 Worker |
| Worker 冲突无法自动解决 | 记录到阻塞记录，标记 Worker 为 Blocked，等待人工介入 |
| 看板状态与 REBASE-STATE.md 不一致 | 以 REBASE-STATE.md 为准，同步看板 |
| 子代理超时未返回 | 检查 branch-2 上的实际 commit，判断进度，决定重新分派或继续等待 |

---

## 12. 子代理须知

> **本节供子代理直接阅读。子代理不读看板，只读 REBASE-PLAN.md。**

### 你是谁

你是 AxonHub rebase 任务的一个 Worker（W1-W6 之一）。

### 你的唯一计划文档

```
/Users/busiji/tool/REBASE-PLAN.md
```

打开它，找到 Section 4 中你的 Worker 编号，里面有：
- 分配给你的 commit hash 列表（按顺序 cherry-pick）
- 你负责的文件范围（写集）
- 冲突解决规则
- 验证命令

### 你的工作分支

```bash
cd /Users/busiji/tool/axonhub
git checkout branch-2
```

### 你的工作步骤

1. 按 commit 列表逐个 cherry-pick
2. 遇冲突 → 按 REBASE-PLAN.md Section 7 通用原则解决
3. 每个 cherry-pick 完成后跑验证命令
4. 全部完成后汇报：成功 / 失败 + 详情

### 你的边界

- **只修改你写集内的文件**
- **不执行 `go generate`**（W6 负责）
- **不修改 `branch-1`**
- **不碰其他 Worker 的文件**
- **llm/ 是独立 Go module**（W4 注意：go 命令在 `llm/` 目录下执行）

---

## 13. 用户触发指令

> 用户只需要在对话中发送以下内容即可启动/接力任务。不需要写其他任何东西。

### 触发格式

```
执行 https://github.com/users/hdot123/projects/15
```

就这一行。主线程收到后自动完成以下所有事情。

### 主线程收到触发后自动执行

```
用户发送：执行 https://github.com/users/hdot123/projects/15
    │
    ├── 1. 读取 /Users/busiji/tool/REBASE-STATE.md 获取当前进度
    │
    ├── 2. 读取看板（gh project item-list）获取所有卡片状态
    │
    ├── 3. 对照 REBASE-STATE.md 和看板，判断当前应该做什么：
    │
    │   ├── P0 = Todo → 直接执行 P0（创建 branch-2）
    │   ├── W1-W5 有 Todo → 并行 spawn_agent 分派（子代理模型：gpt-5.4-mini）
    │   │   ├── 从看板卡片的「分派模板」复制 spawn message
    │   │   └── 每个 Worker 的写集不重叠，可以同时跑
    │   ├── W1-W5 全部 Done，W6 = Todo → 分派 W6（串行，等 W1-W5）
    │   ├── W6 Done，P1 = Todo → 直接执行 P1（merge + push + 清理）
    │   └── 全部 Done → 汇报完成
    │
    ├── 4. 每个 Worker 返回后：
    │   ├── 验证改动范围（git diff --stat）
    │   ├── 跑 go build 验证编译
    │   ├── 更新 REBASE-STATE.md（状态 + 时间戳）
    │   └── 更新看板卡片状态
    │
    └── 5. 向用户汇报当前轮次结果 + 下一步计划
```

### 用户可选附加指令

用户也可以在链接后面追加约束，主线程必须遵守：

| 附加指令 | 含义 |
|----------|------|
| `执行 <链接> 只跑 W3` | 只分派指定 Worker，其他不动 |
| `执行 <链接> 跳过测试` | W6 不跑 go test，只做 cherry-pick + go generate |
| `执行 <链接> dry-run` | 只输出计划不实际执行 |
| `执行 <链接> 验收` | 不分派新任务，只验证已完成的工作 |

不带附加指令时，按 REBASE-STATE.md 的进度自动继续。

---

## 14. CE-01 部署验证

> L2 通过后、L3 之前，必须在 CE-01 上完成远程编译 + 测试 + 部署验证。

### 步骤

```bash
# 1. 推代码
cd /Users/busiji/tool/axonhub
git push origin branch-2

# 2. CE-01 同步
ssh ce-01 'export PATH=$PATH:/usr/local/go/bin:$HOME/go/bin && \
  cd /root/axonhub-ci && git fetch origin && \
  git checkout branch-2 && git reset --hard origin/branch-2'

# 3. 远程编译
ssh ce-01 'export PATH=$PATH:/usr/local/go/bin:$HOME/go/bin && \
  cd /root/axonhub-ci && go build -ldflags "-s -w" -tags=nomsgpack -o axonhub ./cmd/axonhub'

# 4. 远程测试
ssh ce-01 'export PATH=$PATH:/usr/local/go/bin:$HOME/go/bin && \
  cd /root/axonhub-ci && go test ./... -count=1 -timeout 300s'

# 5. 构建镜像
ssh ce-01 'cd /root/axonhub-ci && \
  docker build -t axonhub-hdot:v0.9.38-latest .'

# 6. 重启
ssh ce-01 'cd /root/axonhub-ci && \
  docker stop axonhub-app && docker rm axonhub-app && \
  docker compose up -d axonhub'

# 7. 健康检查
ssh ce-01 'sleep 10 && curl -sf http://localhost:8090/api/health'

# 8. 日志
ssh ce-01 'docker logs axonhub-app --tail 30'
```

CE-01 通过后才执行 L3 最终验收和 P1 merge。
