# 自定义模型 (BYOK) 配置指南

> 更新时间：2026-06-01

## 配置文件位置

- Mac: `~/.factory/settings.json`
- node-22: `/root/.factory/settings.json`

## 当前模型列表

| 模型 | ID | 用途 | Provider |
|------|-----|------|----------|
| GLM-5.1 | custom:GLM-5.1-(node-01) | 主力模型、Mission 编排器 | generic-chat-completion-api |
| GLM-5 | custom:GLM-5-(node-01) | 备用 | generic-chat-completion-api |
| Qwen 3.6 Plus | custom:Qwen-3.6-Plus-(node-01) | Worker、验证 | generic-chat-completion-api |
| Qwen 3.5 Plus | custom:Qwen-3.5-Plus-(node-01) | 备用 Worker | generic-chat-completion-api |
| Kimi K2.5 | custom:Kimi-K2.5-(node-01) | 长文本 | generic-chat-completion-api |
| GPT-5.5 | custom:node1-gpt55 | 已停用 | generic-chat-completion-api |

## 模型端点

所有模型通过统一代理端点访问：`https://REDACTED.ts.net/v1`

## API Key 管理

- Key 存储在 1Password: `Droid BYOK / node-22 / API Key` (vault: sever)
- 本地 Mac 和 node-22 使用不同的 key
- Key 配置在 `settings.json` 的 `apiKey` 字段

## 默认模型设置

```json
{
  "sessionDefaultSettings": {
    "model": "custom:GLM-5.1-(node-01)",
    "reasoningEffort": "high"
  },
  "missionModelSettings": {
    "workerModel": "custom:Qwen-3.6-Plus-(node-01)",
    "validationWorkerModel": "custom:Qwen-3.6-Plus-(node-01)"
  },
  "missionOrchestratorModel": "custom:GLM-5.1-(node-01)"
}
```

## 切换模型

在 Droid session 中使用 `/model` 命令切换。
