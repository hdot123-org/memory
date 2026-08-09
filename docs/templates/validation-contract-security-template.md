# Validation Contract 安全断言模板

> 编排器在创建 Mission 的 validation-contract.md 时，必须参考本模板为每个涉及攻击面的 feature 添加安全断言。

## 攻击面清单

| 攻击面 | 断言前缀 | 必须断言的内容 |
|--------|----------|---------------|
| 用户输入 | VAL-SEC-INP | 所有外部输入经过校验/转义，无注入路径 |
| 认证/授权 | VAL-SEC-AUTH | 权限检查不可绕过，session 不可伪造 |
| 数据存储 | VAL-SEC-STORE | 敏感数据加密存储，无明文泄露 |
| 外部调用 | VAL-SEC-EXT | 外部 API 响应经过校验，无 SSRF/重定向风险 |
| 文件操作 | VAL-SEC-FILE | 路径不可遍历，文件类型/大小有限制 |
| 并发操作 | VAL-SEC-CONC | 无竞态条件，锁不可死锁 |
| 密钥管理 | VAL-SEC-KEY | 无硬编码密钥，密钥通过环境变量或密钥管理服务获取 |

## 断言格式

每个安全断言在 validation-contract.md 中的格式：

```markdown
### VAL-SEC-XXX: [标题]

**攻击面**: [上表中的分类]
**断言**: [具体的安全要求描述]
**验证方式**: [如何验证此断言通过]
**Worker 自检清单**:
- [ ] [具体检查项1]
- [ ] [具体检查项2]
```

## 安全适用性声明

对于不涉及上述攻击面的纯内部 feature，validation-contract.md 必须显式标注：

```markdown
### VAL-SEC-XXX: 安全适用性声明

**攻击面评估**: 无
**理由**: 本 feature 不涉及外部输入/认证/数据存储/外部调用/文件操作/并发操作。
```

## 引用规则

涉及安全面的 feature，其 `fulfills` 数组必须包含对应的 `VAL-SEC-xxx` ID。
