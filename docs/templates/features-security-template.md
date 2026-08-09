# features.json 安全行为模板

> 编排器在创建 features.json 时，涉及安全面的 feature 必须在 expectedBehavior 中包含安全行为描述。

## expectedBehavior 安全行为模板

```json
{
  "id": "FEAT-XXX",
  "title": "...",
  "expectedBehavior": [
    "...功能行为...",
    "所有外部输入经过 [校验方式]，不存在注入/越权/信息泄露路径",
    "无硬编码密钥或凭证，所有敏感配置通过环境变量获取"
  ],
  "fulfills": ["VAL-BHV-XXX", "VAL-SEC-XXX"]
}
```

## 安全行为必须覆盖的场景

| 场景 | expectedBehavior 必须包含的安全行为 |
|------|-----------------------------------|
| API 端点 | "端点校验所有输入参数，拒绝非法输入，返回统一错误格式" |
| 数据库操作 | "使用参数化查询，不存在 SQL 注入路径" |
| 文件上传 | "校验文件类型和大小，路径不可遍历" |
| 外部 API 调用 | "校验响应状态码和数据格式，处理超时和异常" |
| 用户认证 | "密码不明文存储，session token 不可预测，权限检查不可绕过" |

## 无安全面的 feature

如果 feature 确实不涉及安全面，expectedBehavior 不需要加安全行为，但 fulfills 中必须引用一个 `VAL-SEC-XXX: 安全适用性声明`。
