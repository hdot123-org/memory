# Changelog

## [0.35.0](https://github.com/hdot123-org/memory/compare/v0.34.0...v0.35.0) (2026-08-19)


### Features

* **ci:** watchdog 新增 CI 失败自动取消进行中的 droid-review ([#811](https://github.com/hdot123-org/memory/issues/811)) ([f008c7a](https://github.com/hdot123-org/memory/commit/f008c7aabf518be435d1bc08b091fe4255ee52d3))
* D3 tick 预算守卫（VAL-DRF-004） ([#784](https://github.com/hdot123-org/memory/issues/784)) ([b839b70](https://github.com/hdot123-org/memory/commit/b839b7089fa7650ae02510caa67f710b2c04ec4a))
* **evolution:** D1 反向漂移守望——孤儿 issue 分类与自动补救 ([#780](https://github.com/hdot123-org/memory/issues/780)) ([054cf34](https://github.com/hdot123-org/memory/commit/054cf3483cb09164a72b5d8b8ddd0a8b239afffa))
* 死锁出口信任链改用 Linear 评论 + GATE A 4.5/4.7 裁决落地 ([#794](https://github.com/hdot123-org/memory/issues/794)) ([680f14b](https://github.com/hdot123-org/memory/commit/680f14bea9a169f56a9d6ed4bd18c0e2e9b63cd5))


### Bug Fixes

* **branch-cleanup:** 通知守卫——deleted_count=0 不建单（VAL-NTF-001） ([#816](https://github.com/hdot123-org/memory/issues/816)) ([d56f3c8](https://github.com/hdot123-org/memory/commit/d56f3c8c1880f7149dc538818eff6f03314abafd))
* coverage gap finder 兼容 editable install 的 XML 路径，CI 复用门禁 pytest 产物 ([#825](https://github.com/hdot123-org/memory/issues/825)) ([4749f1b](https://github.com/hdot123-org/memory/commit/4749f1b4263e6cd2548be693e15164fd33f0581e))
* **evolution:** 反向漂移守望生产级修复——孤儿分类从 no-op 变为可用并补齐防护门禁 (INFRA-403) ([#819](https://github.com/hdot123-org/memory/issues/819)) ([b2756da](https://github.com/hdot123-org/memory/commit/b2756da85269b87705967885015950d15743a413))
* **evolution:** 正向漂移守望改用真实输入与配额分类（INFRA-410） ([#826](https://github.com/hdot123-org/memory/issues/826)) ([d0718c9](https://github.com/hdot123-org/memory/commit/d0718c92daf655804a0ef359c6d35565a43b548a))
* **gate:** PR 引用检查支持逗号列表+None body 防御+test_dup_004 突变敏感化 ([#807](https://github.com/hdot123-org/memory/issues/807)) ([debc617](https://github.com/hdot123-org/memory/commit/debc617b489082a5ba38282795031ee7fcf8bbe1))
* PR 引用正则扩展支持全部 9 种 GitHub closing keyword 变体 ([#803](https://github.com/hdot123-org/memory/issues/803)) ([94e6175](https://github.com/hdot123-org/memory/commit/94e6175537e526c59d9c7bd6deffbc1ff8ea7aee))
* repo health check 突变用例夹具化，消除 xdist 并行竞态 ([#809](https://github.com/hdot123-org/memory/issues/809)) ([62ac3af](https://github.com/hdot123-org/memory/commit/62ac3af82cc148abb12dec6f53ccfffbbe242ce1))
* **scanner:** VAL-DUP-004 critical 回归先于去重丢弃修复 ([#799](https://github.com/hdot123-org/memory/issues/799)) ([fbbe083](https://github.com/hdot123-org/memory/commit/fbbe08390ebdf6919bf51aef85fd8ed47b6a52e0))
* **scanner:** 修复 critical 回归被 dedup 残留吞没的两条路径 (INFRA-396) ([#804](https://github.com/hdot123-org/memory/issues/804)) ([c875e39](https://github.com/hdot123-org/memory/commit/c875e395729d86cac16ed3a64f6be3df40cae2e0))
* 为反向漂移守望添加三重安全防护（PR [#780](https://github.com/hdot123-org/memory/issues/780) droid-review P1 修复） ([#817](https://github.com/hdot123-org/memory/issues/817)) ([ddf17e0](https://github.com/hdot123-org/memory/commit/ddf17e0d872301d20f3af4f96f2e1a5c6f6ddf22))
* 修正夹具映射测试断言 4/7 错误 ([#800](https://github.com/hdot123-org/memory/issues/800)) ([0b26c26](https://github.com/hdot123-org/memory/commit/0b26c26547b0a43bcceab3baa5ebdef2a5166edd))
* 退休被取代分支，补齐 PR 引用检查逗号列表与 None body 回归测试 (INFRA-401) ([#814](https://github.com/hdot123-org/memory/issues/814)) ([5a6d057](https://github.com/hdot123-org/memory/commit/5a6d05715b6390d866fb6a4a45a1dab07d4fcc0a))

## [0.34.0](https://github.com/hdot123-org/memory/compare/v0.33.1...v0.34.0) (2026-08-18)


### Features

* **notifications:** 通知 issue TTL 自动关闭 (VAL-NTF-002) ([#786](https://github.com/hdot123-org/memory/issues/786)) ([8f08be2](https://github.com/hdot123-org/memory/commit/8f08be2bdc24035af797b5f0f41f2d9121e3834e))
* 实现 D2 正向漂移守望（VAL-DRF-001） ([#783](https://github.com/hdot123-org/memory/issues/783)) ([af06493](https://github.com/hdot123-org/memory/commit/af0649302b7c8f7192643ef7d3b25579e4c11194))
* 添加 PR 引用一致性检查器 (C1) ([#765](https://github.com/hdot123-org/memory/issues/765)) ([a91bf9f](https://github.com/hdot123-org/memory/commit/a91bf9fd44d53b24bb52a551e6968f8c75fabf18))
* 添加通知 Linear 隔离测试 (VAL-NTF-003/004/005) ([#792](https://github.com/hdot123-org/memory/issues/792)) ([5beffeb](https://github.com/hdot123-org/memory/commit/5beffeb2ff9884d9c916de8693925829b9c0e082))


### Bug Fixes

* **branch-cleanup:** squash 合并分支误保护修复——内容包含检查 (INFRA-383) ([#779](https://github.com/hdot123-org/memory/issues/779)) ([2e97ed8](https://github.com/hdot123-org/memory/commit/2e97ed8230532216d20a8339a25cacfe2094f672))
* **branch-cleanup:** 分支退役清单——被等价实现取代的孤儿分支可审计清理 (INFRA-388) ([#788](https://github.com/hdot123-org/memory/issues/788)) ([6565ac6](https://github.com/hdot123-org/memory/commit/6565ac696a132c84acb063b8a84e77d07e5d4437))
* **branch-cleanup:** 跟踪 issue 去重——单一 tracking issue 取代每次运行新建 (INFRA-385) ([#782](https://github.com/hdot123-org/memory/issues/782)) ([66d0c2c](https://github.com/hdot123-org/memory/commit/66d0c2c52008e5166d66085f989e48a48b9124cf))
* **branch-cleanup:** 退役 feat/pr-ref-gate-ci-wiring——job 级接线已被 step 级实现取代 (INFRA-391) ([#795](https://github.com/hdot123-org/memory/issues/795)) ([1c14acf](https://github.com/hdot123-org/memory/commit/1c14acf322ca67bff65bab6e6c1cbc58d753896e))
* **evolution:** 漂移守望日志显式化 + 终态吸收卫生优化 ([#798](https://github.com/hdot123-org/memory/issues/798)) ([e65ea7c](https://github.com/hdot123-org/memory/commit/e65ea7cc1548e1b5c9974c68c1645a5c133761e3))
* **test:** 修复 load_key mock 泄漏导致 test_resign_no_key_fails 随机顺序依赖 ([#796](https://github.com/hdot123-org/memory/issues/796)) ([8edc3df](https://github.com/hdot123-org/memory/commit/8edc3df098c615fba632b834c603a9b9a5ae3b10))
* **webhook:** status=failed 死锁出口——复用 stale-orphan counter 阻断无限 retrigger (INFRA-371) ([#763](https://github.com/hdot123-org/memory/issues/763)) ([7ba13b3](https://github.com/hdot123-org/memory/commit/7ba13b343272be83917f67d1212e00deae39f0c2))


### Documentation

* **agents:** mission 异步合并纪律——会话退出合并关键路径 ([#766](https://github.com/hdot123-org/memory/issues/766)) ([01012c7](https://github.com/hdot123-org/memory/commit/01012c7a59e50baac0823df02af60fbfbe768ae2))
* **issue-flow:** 补记通知 Issue TTL 自愈机制（VAL-NTF-002/INFRA-389） ([#789](https://github.com/hdot123-org/memory/issues/789)) ([43ee403](https://github.com/hdot123-org/memory/commit/43ee403f10c0dbce80379b11acdd1c3bf4d67a88))
* **plans:** GitHub API 503 自动重试技术债登记（TD-503-01/02/03） ([#770](https://github.com/hdot123-org/memory/issues/770)) ([96e083a](https://github.com/hdot123-org/memory/commit/96e083ace7115228366eb36653e260223144b31b))
* **plans:** TD-503-01 状态闭环——watchdog 已由 PR [#777](https://github.com/hdot123-org/memory/issues/777) 交付（INFRA-386） ([#785](https://github.com/hdot123-org/memory/issues/785)) ([81bf230](https://github.com/hdot123-org/memory/commit/81bf23009c19239f3ad7c22afbd3aead8f0fff87))

## [0.33.1](https://github.com/hdot123/memory/compare/v0.33.0...v0.33.1) (2026-08-17)


### Bug Fixes

* **evolution_scanner:** 去重黑洞修复——closed issue 仅 7 天内参与去重 ([#759](https://github.com/hdot123/memory/issues/759)) ([504d621](https://github.com/hdot123/memory/commit/504d621d73cf1d5a98d16025879edaea6c265962))
* **evolution:** Linear 移除 attachmentType 字段致 GraphQL 400，信任链永久 fail-closed，改用 sourceType (INFRA-372) ([#760](https://github.com/hdot123/memory/issues/760)) ([3023687](https://github.com/hdot123/memory/commit/30236878b5048d54a9e6bb7258ae46838a43b418))

## [0.33.0](https://github.com/hdot123/memory/compare/v0.32.0...v0.33.0) (2026-08-17)


### Features

* **webhook:** 死锁出口/retrigger 双验证/security-gate 密钥正则规避 ([#738](https://github.com/hdot123/memory/issues/738)) ([0d061c9](https://github.com/hdot123/memory/commit/0d061c9bb6f3ff088972e33b7e1f57770721415f))


### Bug Fixes

* anchor_gate 日志写入失败不再静默吞掉，改为 stderr 告警 (INFRA-359) ([#743](https://github.com/hdot123/memory/issues/743)) ([ae2660d](https://github.com/hdot123/memory/commit/ae2660dd195fea153378ccabfdfb2f2e2dfbfe25))
* boundary_guard 只扫描 git-tracked 文件，排除 untracked 误报 ([#744](https://github.com/hdot123/memory/issues/744)) ([727db8a](https://github.com/hdot123/memory/commit/727db8a60bda0468066e0fc3cccc6b83448e9992))
* **webhook:** stale 孤儿 issue 连续 5 tick E4 阻挡后执行 Linear canceled fallback 出口 (INFRA-310) ([#747](https://github.com/hdot123/memory/issues/747)) ([2bfaedf](https://github.com/hdot123/memory/commit/2bfaedf579347e858e24f3f2b9287f405bb2068a))
* **webhook:** 死锁出口 teams(first:1) 根因修复——改 team(id:$teamId) 精确查询 + 防御性判空 ([#746](https://github.com/hdot123/memory/issues/746)) ([fb1573d](https://github.com/hdot123/memory/commit/fb1573d1569e853b9bb75037ca58a5d9837e3e62))
* **webhook:** 降级派发命令移除 --mission 防止 SIGTERM 僵尸累积 ([#741](https://github.com/hdot123/memory/issues/741)) ([1cdad06](https://github.com/hdot123/memory/commit/1cdad06f168271072041580f0cdf77f5e90e5c13))


### Documentation

* **lessons:** webhook mission 超时绞杀教训入库 (PR [#741](https://github.com/hdot123/memory/issues/741) 收尾) ([#745](https://github.com/hdot123/memory/issues/745)) ([0bf73a5](https://github.com/hdot123/memory/commit/0bf73a59360c47787c400080b683000235726d3a))

## [0.32.0](https://github.com/hdot123/memory/compare/v0.31.0...v0.32.0) (2026-08-16)


### Features

* **webhook:** 镜像定位锚点化——§4b 与 GATE A 4.5/4.6 改用 linear-linkback 锚点+label 双闸+一致性校验 ([#737](https://github.com/hdot123/memory/issues/737)) ([2950659](https://github.com/hdot123/memory/commit/29506597f08af266743b7dfd4042178954865e0e))


### Bug Fixes

* droid-review CI 防挂死加固（timeout + 凭证预检 + 清理无效输入） ([#733](https://github.com/hdot123/memory/issues/733)) ([6a7d21e](https://github.com/hdot123/memory/commit/6a7d21ec82717b878238b844c3bfc71c4c92d848))
* 修复 m1 scrutiny 4 项非 blocking 发现 ([#736](https://github.com/hdot123/memory/issues/736)) ([ce696e3](https://github.com/hdot123/memory/commit/ce696e33858408e77484c11afff4414279ad2e8c))


### Documentation

* 修正 issue-flow.md 中对已删除 GAP-B 脚本的过时引用 ([#735](https://github.com/hdot123/memory/issues/735)) ([b0360c0](https://github.com/hdot123/memory/commit/b0360c0bb27134c831bec1348bd1ea7a29498d1c))

## [0.31.0](https://github.com/hdot123/memory/compare/v0.30.0...v0.31.0) (2026-08-16)


### Features

* webhook 脚本版本化与同步基础设施 (m1 地基) ([#731](https://github.com/hdot123/memory/issues/731)) ([e7e5f85](https://github.com/hdot123/memory/commit/e7e5f85df4da85a9ccc32ac85fcc72018de2ef7a))


### Bug Fixes

* auto-merge 合并改用 DISPATCH_TOKEN，修复 push 事件被抑制导致发版链路断裂 ([#712](https://github.com/hdot123/memory/issues/712)) ([8b0a91f](https://github.com/hdot123/memory/commit/8b0a91f46dd3fa5e84e85505ce9fb8e23020238d))

## [0.30.0](https://github.com/hdot123/memory/compare/v0.29.0...v0.30.0) (2026-08-15)


### Features

* heartbeat 自愈机制（P1）- 异常消失自动关闭告警 ([#680](https://github.com/hdot123/memory/issues/680)) ([dbf9e3a](https://github.com/hdot123/memory/commit/dbf9e3a5cd875dfb3f3d805f46f98604eaedaa48))
* **heartbeat:** 加固 VAL-HB-004 信任链 fail-safe 机制 ([#696](https://github.com/hdot123/memory/issues/696)) ([f3a5031](https://github.com/hdot123/memory/commit/f3a50312175f7e04130d3848b467a02b61f2affe))
* P2 降噪 - info 级持续 finding 输出 suppress.json 提案 ([#684](https://github.com/hdot123/memory/issues/684)) ([6bbab1b](https://github.com/hdot123/memory/commit/6bbab1b4f625a4b3a6f077cb5d8e0db80e4f7847))


### Bug Fixes

* P2 提案链健壮性收尾——过期 suppress 尊重 expires + main 守护 ([#698](https://github.com/hdot123/memory/issues/698)) ([fb514d8](https://github.com/hdot123/memory/commit/fb514d8e4af6d965f419a4af83066d750876114d))
* 扫描器关单信任链加固(linkback 两级提取 fail-closed + 输出骤降防护) ([#670](https://github.com/hdot123/memory/issues/670)) ([12ac994](https://github.com/hdot123/memory/commit/12ac994db53069bed9c65444a7a26bc8027d276d))


### Documentation

* 补录 08-14 振荡复发教训与派发会话关单规矩 ([#689](https://github.com/hdot123/memory/issues/689)) ([86b57c9](https://github.com/hdot123/memory/commit/86b57c98e4f2793bc6b1cbd5240676824d96d509))
* 补录演化管道收尾——心跳自愈/suppress 提案/GATE A 同步型放行链路 ([#709](https://github.com/hdot123/memory/issues/709)) ([f0a5aa7](https://github.com/hdot123/memory/commit/f0a5aa798383b8fa1baccbc93d0e34dd3da4b3e3))

## [0.29.0](https://github.com/hdot123/memory/compare/v0.28.0...v0.29.0) (2026-08-15)


### Features

* suppress.json expires 字段治理 (VAL-SUPPRESS-001..003) ([#674](https://github.com/hdot123/memory/issues/674)) ([e1a8604](https://github.com/hdot123/memory/commit/e1a8604e3055a358e5a5f1c4addb0c0c4cf5026e))


### Bug Fixes

* 为 code_hygiene 类别新增独立第三配额池 ([#672](https://github.com/hdot123/memory/issues/672)) ([bb42ea2](https://github.com/hdot123/memory/commit/bb42ea241742c846fc0298d3c0633e1e51dcd0c7))
* 新增 tests/__init__.py 防止 site-packages 野生 tests 包遮蔽 ([#651](https://github.com/hdot123/memory/issues/651)) ([3a10086](https://github.com/hdot123/memory/commit/3a1008684bae30dff988e448ea7312577d0e006f))

## [0.28.0](https://github.com/hdot123/memory/compare/v0.27.0...v0.28.0) (2026-08-14)


### Features

* evolution_scanner suppress.json 支持 expires 过期机制 ([#631](https://github.com/hdot123/memory/issues/631)) ([81e25f6](https://github.com/hdot123/memory/commit/81e25f66ecbb67b12d644c9132d7ae00a61fd7d5))


### Bug Fixes

* evolution scanner 支持按工具配置超时并修复 code_hygiene_audit 60s 超时 (INFRA-278) ([#636](https://github.com/hdot123/memory/issues/636)) ([5b991e7](https://github.com/hdot123/memory/commit/5b991e76c46c0a31030b77486d485788cf94901b))
* evolution scanner 支持按工具配置超时并修复 code_hygiene_audit 60s 超时 (INFRA-278) ([#638](https://github.com/hdot123/memory/issues/638)) ([e2fee82](https://github.com/hdot123/memory/commit/e2fee828599bd64a40ed58c4be30e90e9143356b))
* 修复 suppress 过期判断使用本地时区而非 UTC ([#632](https://github.com/hdot123/memory/issues/632)) ([8cd8d54](https://github.com/hdot123/memory/commit/8cd8d54e51ae14ea4d5bba361bd7ccb87829e12c))
* 修复剩余 shellcheck 存在性检查的死代码 (INFRA-274) ([#626](https://github.com/hdot123/memory/issues/626)) ([7dd2fe6](https://github.com/hdot123/memory/commit/7dd2fe60ace2754a43e9ebf75f3ed62cd28e3097))


### Performance Improvements

* 删除 Phase 2 跨名检测解决 O(n²) 性能问题 ([#628](https://github.com/hdot123/memory/issues/628)) ([5afd502](https://github.com/hdot123/memory/commit/5afd50204e68e5bc0a14d3469cb89f2e52a03010))

## [0.27.0](https://github.com/hdot123/memory/compare/v0.26.0...v0.27.0) (2026-08-14)


### Features

* code_hygiene_audit 新增 AST 重复检测 + TODO 正则误报修复 ([#622](https://github.com/hdot123/memory/issues/622)) ([f207bb5](https://github.com/hdot123/memory/commit/f207bb5f58341a865ddc0334e5a6e780d5513acb))
* code_hygiene_audit 新增 TODO 无引用检测 ([#616](https://github.com/hdot123/memory/issues/616)) ([481e5ac](https://github.com/hdot123/memory/commit/481e5ac1912587e12b1196ae4b2819fab8b23ce9))
* code_hygiene_audit 新增跨名 AST 重复检测，修复 TODO 正则词边界误报 (INFRA-273) ([#623](https://github.com/hdot123/memory/issues/623)) ([3bb888f](https://github.com/hdot123/memory/commit/3bb888fc8bcdee3d45e91c3c94e4cbcbe76d16c5))


### Bug Fixes

* check_todos 使用 tokenize 识别真实注释，排除字符串字面量误报 (INFRA-272) ([#620](https://github.com/hdot123/memory/issues/620)) ([c4e5ed1](https://github.com/hdot123/memory/commit/c4e5ed12a8be8628d694e444f5373621771d127e))
* evolution scanner check_trigger_droid 增加稳定性重试避免假阳性 (INFRA-264) ([#612](https://github.com/hdot123/memory/issues/612)) ([31a9363](https://github.com/hdot123/memory/commit/31a9363659242871c707f1fbb2adf3c19dab12ee))
* HACK 标记补充 Issue 引用豁免与 TODO/FIXME 保持一致 (INFRA-270) ([#617](https://github.com/hdot123/memory/issues/617)) ([11efce5](https://github.com/hdot123/memory/commit/11efce581432f373eadc909561c708f05ff5ec12))
* P1-2 硬退出排除 daily_audit 避免纯基础设施 tick 误报 (INFRA-268) ([#613](https://github.com/hdot123/memory/issues/613)) ([f12b3f5](https://github.com/hdot123/memory/commit/f12b3f54c94dc09b9cffc86798b56ba487d805c3))
* scanner 排除 daily_audit 类 finding 避免基础设施误报 ([#611](https://github.com/hdot123/memory/issues/611)) ([58184f9](https://github.com/hdot123/memory/commit/58184f9b97b9ac061cb9d192519bb0f8e506c34a))
* 修复 8 处类型化异常静默吞没 (INFRA-262) ([#601](https://github.com/hdot123/memory/issues/601)) ([fb4955f](https://github.com/hdot123/memory/commit/fb4955fc7f9003b3c102ac47c2861077a12e1fa6))
* 修复 check_repositories_yml 误报 EVOLUTION_ROUTING_MISCONFIG (INFRA-266) ([#607](https://github.com/hdot123/memory/issues/607)) ([34d073e](https://github.com/hdot123/memory/commit/34d073efc9162b0d98989ef8dfb015a14fd73b72))
* 源仓库跳过完整性清单检查，消除 HASH_MISMATCH 误报 (INFRA-263) ([#606](https://github.com/hdot123/memory/issues/606)) ([3a18c05](https://github.com/hdot123/memory/commit/3a18c05f6f9a896c0e0ca8f06e50458d8fd7df0d))
* 补充 resolve_pr_ref 函数消除 heartbeat 异常 (INFRA-267) ([#610](https://github.com/hdot123/memory/issues/610)) ([644ab68](https://github.com/hdot123/memory/commit/644ab685c50624b26682e83532ec0716ffd674a5))


### Documentation

* 记录 infrastructure-inventory 下线同步教训 (INFRA-265) ([#609](https://github.com/hdot123/memory/issues/609)) ([ef5880a](https://github.com/hdot123/memory/commit/ef5880af2126dbaee17af157172a7a545ebf6574))

## [0.26.0](https://github.com/hdot123/memory/compare/v0.25.0...v0.26.0) (2026-08-13)


### Features

* 实现 code_hygiene_audit CLI 工具检测静默异常吞没模式 ([#567](https://github.com/hdot123/memory/issues/567)) ([4aac985](https://github.com/hdot123/memory/commit/4aac9854cf05e2da5b5120cd5668207c28ab0b3e))


### Bug Fixes

* session_end_logger 剩余 sys.exit(0) 统一改为 os._exit(0) ([#565](https://github.com/hdot123/memory/issues/565)) ([8ceae04](https://github.com/hdot123/memory/commit/8ceae04abcd8d8e91be182118bdac1130bad3243))
* 修复 apply_residue_plan.py 中 SILENT_SWALLOW 静默异常吞没 ([#571](https://github.com/hdot123/memory/issues/571)) ([6324073](https://github.com/hdot123/memory/commit/632407332dfd65f60642725990abeab48ccdb6a8))
* 修复 error_logger.py 中 _detect_calling_script 静默异常吞没 (INFRA-245) ([#585](https://github.com/hdot123/memory/issues/585)) ([a44d28b](https://github.com/hdot123/memory/commit/a44d28b2d87f5d03808467b361076f99a18ba987))
* 修复 telemetry_bridge.py 静默异常吞没 (INFRA-258) ([#593](https://github.com/hdot123/memory/issues/593)) ([5506f69](https://github.com/hdot123/memory/commit/5506f6917bda07d24b73c17167e2666ea5f83935))
* 修复 test_logger_budget_scan.py 中 stdin 清理静默异常吞没 (INFRA-259) ([#592](https://github.com/hdot123/memory/issues/592)) ([842cad2](https://github.com/hdot123/memory/commit/842cad2ca2c6d30925c28b9c42304cdb68c51533))
* 升级 error_logger.py SILENT_SWALLOW 修复至 warning 级别 + stderr fallback ([#599](https://github.com/hdot123/memory/issues/599)) ([df36c80](https://github.com/hdot123/memory/commit/df36c806681262f2f78b606da0a39846ead2c7e6))
* 批量修复 11 处 SILENT_SWALLOW 静默异常吞没 (INFRA-261) ([#597](https://github.com/hdot123/memory/issues/597)) ([c2f2c7d](https://github.com/hdot123/memory/commit/c2f2c7da5c691efe26e44fd0e1f3ba473bfa9c75))

## [0.25.0](https://github.com/hdot123/memory/compare/v0.24.1...v0.25.0) (2026-08-13)


### Features

* 为 4 个 hook 工具添加 telemetry import，覆盖率提升至 100% ([#562](https://github.com/hdot123/memory/issues/562)) ([2e04126](https://github.com/hdot123/memory/commit/2e041261901ec8a7e75078f59c17f2cd4309ebc9))


### Bug Fixes

* 信号处理器改用 os._exit 避免 telemetry atexit Traceback 污染 ([#563](https://github.com/hdot123/memory/issues/563)) ([bfeb6d2](https://github.com/hdot123/memory/commit/bfeb6d2ac042ce34fdbfdb9f18d6660b38e79367))


### Performance Improvements

* 审计脚本排除 .venv 目录并优化目录遍历 ([#561](https://github.com/hdot123/memory/issues/561)) ([0348135](https://github.com/hdot123/memory/commit/034813551242a83e00d62bf56d0d1a260504e937))

## [0.24.1](https://github.com/hdot123/memory/compare/v0.24.0...v0.24.1) (2026-08-12)


### Bug Fixes

* 统一 gh pr view 失败路径为 fail-closed 策略 ([#554](https://github.com/hdot123/memory/issues/554)) ([67c05d0](https://github.com/hdot123/memory/commit/67c05d0a14f9bf5ff4cb7715e9bf8ff3b8944072))
* 统一 Linear API 错误路径为 fail-closed 策略 ([#553](https://github.com/hdot123/memory/issues/553)) ([1f152a6](https://github.com/hdot123/memory/commit/1f152a64f8c641c0c154fabd4294f74e3f40b1e7))

## [0.24.0](https://github.com/hdot123/memory/compare/v0.23.1...v0.24.0) (2026-08-12)


### Features

* 新增 fix-has-test CI 门禁 ([#550](https://github.com/hdot123/memory/issues/550)) ([fc1331c](https://github.com/hdot123/memory/commit/fc1331c697e9d66373130de888e7ae746db495b7))


### Bug Fixes

* 修复 evolution scanner close/reopen 循环（Linear 终端态检查 + 抑制策略） ([#551](https://github.com/hdot123/memory/issues/551)) ([f967c7f](https://github.com/hdot123/memory/commit/f967c7fb382cdea8f0a47d64b65fe38c1bf24d6e))

## [0.23.1](https://github.com/hdot123/memory/compare/v0.23.0...v0.23.1) (2026-08-12)


### Bug Fixes

* heartbeat 改用 gh run list 替代缓存依赖，修复误报流水线异常 (INFRA-213) ([#521](https://github.com/hdot123/memory/issues/521)) ([ea7377a](https://github.com/hdot123/memory/commit/ea7377a496ede17163476d60df8d6fb5d0d6509b))

## [0.23.0](https://github.com/hdot123/memory/compare/v0.22.2...v0.23.0) (2026-08-12)


### Features

* branch-cleanup 支持 PR 关闭即时触发 (INFRA-211) ([#517](https://github.com/hdot123/memory/issues/517)) ([462c251](https://github.com/hdot123/memory/commit/462c251c7c04021bd10a84860fc295a6aa0bc502))
* **branch-cleanup:** 提取内联脚本 + 修复 IMMEDIATE_MODE 作用域 bug (M2) ([#531](https://github.com/hdot123/memory/issues/531)) ([ed59fb7](https://github.com/hdot123/memory/commit/ed59fb75856296aae9cf32dd514284b730558a20))
* **ci:** 添加 shellcheck/actionlint pre-commit hooks + CI lint 门禁 (M2) ([#532](https://github.com/hdot123/memory/issues/532)) ([46f476f](https://github.com/hdot123/memory/commit/46f476f5083a8fd2709366512b9bce7ef623ae05))
* **evolution:** 实现 Issue 重开机制 (M1 Trust Chain) ([#525](https://github.com/hdot123/memory/issues/525)) ([4ceee9a](https://github.com/hdot123/memory/commit/4ceee9a35267e2a5c8258d7e1dd913a74d8c59a6))
* **evolution:** 实现 PR-Merged Verification (M1 Trust Chain) ([#524](https://github.com/hdot123/memory/issues/524)) ([7a9e6a4](https://github.com/hdot123/memory/commit/7a9e6a4b4b0cfec0078556bdb2de70bee4678cbe))


### Bug Fixes

* auto-merge 改用 workflow_run + schedule 触发，修复 CI 全绿后不自动合并 (INFRA-212) ([#519](https://github.com/hdot123/memory/issues/519)) ([15e93a9](https://github.com/hdot123/memory/commit/15e93a9a0dd7acc1a362821381f2e80fdbaae3e7))
* branch-cleanup 增加独有 commit 安全检查，保护未合并分支 (INFRA-214) ([#523](https://github.com/hdot123/memory/issues/523)) ([155d507](https://github.com/hdot123/memory/commit/155d507688c45029b2bf7ac4d718e4d762719f30))
* check_droid_review.sh 对 dependabot 的 skipped 结论放行 ([#544](https://github.com/hdot123/memory/issues/544)) ([f0772b6](https://github.com/hdot123/memory/commit/f0772b69e1dda918150de81363f9f7f93f80cd4d))
* **ci:** check_droid_review.sh 允许 Dependabot PR 在 droid-review 跳过时合并 (INFRA-222) ([#545](https://github.com/hdot123/memory/issues/545)) ([fc7c6e6](https://github.com/hdot123/memory/commit/fc7c6e64d897a2a18e4f24d6b21bb86f5cb1f102))
* **evolution:** PR-Merged Verification 支持跨仓库 PR，补全 --repo 参数 (INFRA-215) ([#526](https://github.com/hdot123/memory/issues/526)) ([8e01224](https://github.com/hdot123/memory/commit/8e01224a8265996bf80c784e5cf482e74191534e))
* **evolution:** 修复 VAL-CROSS-025 测试 subprocess 使用错误 Python 版本 (INFRA-218) ([#530](https://github.com/hdot123/memory/issues/530)) ([cc7c220](https://github.com/hdot123/memory/commit/cc7c220cabd36d03b6b6e6b8af8295cde936255b))
* **evolution:** 排除 self-audit 类别 finding 的自动关闭，修复 heartbeat 反复抖动循环 (INFRA-216) ([#529](https://github.com/hdot123/memory/issues/529)) ([41648de](https://github.com/hdot123/memory/commit/41648deaa4426faec84b3b5ac11e264f8187075c))
* 为 evolution-heartbeat workflow 添加标签创建步骤 (INFRA-209) ([#514](https://github.com/hdot123/memory/issues/514)) ([4d05f73](https://github.com/hdot123/memory/commit/4d05f739ace17b8c8403e8ad04a13eb68700dab9))
* 修复 branch_cleanup.sh 唯一 commit 计数使用对称差集导致已合并分支被误保护 (INFRA-220) ([#543](https://github.com/hdot123/memory/issues/543)) ([b8e7ed4](https://github.com/hdot123/memory/commit/b8e7ed469570bf883d49b914471aadcc61d0d154))

## [0.22.2](https://github.com/hdot123/memory/compare/v0.22.1...v0.22.2) (2026-08-11)


### Bug Fixes

* 为 check_reverse_closure 的 findings 变量添加类型标注 (INFRA-207) ([#511](https://github.com/hdot123/memory/issues/511)) ([ee724f5](https://github.com/hdot123/memory/commit/ee724f55b79216db8543cc8776d2c21863db337e))

## [0.22.1](https://github.com/hdot123/memory/compare/v0.22.0...v0.22.1) (2026-08-11)


### Bug Fixes

* 解决 PR [#507](https://github.com/hdot123/memory/issues/507) merge conflict ([#509](https://github.com/hdot123/memory/issues/509)) ([0076ab8](https://github.com/hdot123/memory/commit/0076ab81df2877bed53b879ff72e545b2b9af1b2))

## [0.22.0](https://github.com/hdot123/memory/compare/v0.21.0...v0.22.0) (2026-08-11)


### Features

* 添加 evolution heartbeat 独立健康监控管道 (INFRA-204) ([#504](https://github.com/hdot123/memory/issues/504)) ([3188c7e](https://github.com/hdot123/memory/commit/3188c7e3f55863bafc11d53cd549664acf5f2280))

## [0.21.0](https://github.com/hdot123/memory/compare/v0.20.0...v0.21.0) (2026-08-11)


### Features

* 添加 evolution heartbeat 独立监控管道健康 (INFRA-202) ([#500](https://github.com/hdot123/memory/issues/500)) ([c494ab1](https://github.com/hdot123/memory/commit/c494ab1a837945cc6b8299d2bd413decc7b6fbe7))

## [0.20.0](https://github.com/hdot123/memory/compare/v0.19.6...v0.20.0) (2026-08-11)


### Features

* **evolution:** [INFRA-175] 新增 GitHub→Linear 反向补偿工具，修复 Linear 僵尸 Issue ([#490](https://github.com/hdot123/memory/issues/490)) ([5b9b0de](https://github.com/hdot123/memory/commit/5b9b0de7310a3bb1c8536e1a446cea2b888ced30))


### Bug Fixes

* 修复配额饥饿问题，self_audit 独立配额池 (INFRA-198) ([#497](https://github.com/hdot123/memory/issues/497)) ([27aa1ee](https://github.com/hdot123/memory/commit/27aa1eed001ef6c353b2ff4ef6d723b5100af860))

## [0.19.6](https://github.com/hdot123/memory/compare/v0.19.5...v0.19.6) (2026-08-11)


### Bug Fixes

* 添加 reconcile_in_progress 对账机制和幂等性守卫 (Fixes [#456](https://github.com/hdot123/memory/issues/456)) ([#491](https://github.com/hdot123/memory/issues/491)) ([5ce7811](https://github.com/hdot123/memory/commit/5ce7811eade8bd5151829213630343582bc71513))

## [0.19.5](https://github.com/hdot123/memory/compare/v0.19.4...v0.19.5) (2026-08-11)


### Bug Fixes

* 添加 auto_close 优雅期防止误关闭 (INFRA-455) ([#478](https://github.com/hdot123/memory/issues/478)) ([98b0061](https://github.com/hdot123/memory/commit/98b006123ddcc38547c41d529900ebaeb5a46be1))

## [0.19.4](https://github.com/hdot123/memory/compare/v0.19.3...v0.19.4) (2026-08-11)


### Documentation

* 完善 trigger-droid.sh 事件过滤文档，记录 Comment.create 全过滤 (INFRA-180) ([#485](https://github.com/hdot123/memory/issues/485)) ([4dfb926](https://github.com/hdot123/memory/commit/4dfb926793de6edc0740854a544acdef5d4ef6a1))

## [0.19.3](https://github.com/hdot123/memory/compare/v0.19.2...v0.19.3) (2026-08-11)


### Bug Fixes

* **guard:** [INFRA-191] 扩展不可见字符剥离范围至 Cs/Co 类别并抑制空预览误报日志 ([#482](https://github.com/hdot123/memory/issues/482)) ([f919586](https://github.com/hdot123/memory/commit/f9195868227ab37203f7f0301f7e0c39efdff0f1))

## [0.19.2](https://github.com/hdot123/memory/compare/v0.19.1...v0.19.2) (2026-08-11)


### Bug Fixes

* get_open_issues 查询 open + closed 状态防止重复创建 issue ([#477](https://github.com/hdot123/memory/issues/477)) ([59bd3c9](https://github.com/hdot123/memory/commit/59bd3c91593394a81358fac1c4cd796d0eb3e210)), closes [#454](https://github.com/hdot123/memory/issues/454)

## [0.19.1](https://github.com/hdot123/memory/compare/v0.19.0...v0.19.1) (2026-08-11)


### Bug Fixes

* 标记 llm_api_error 错误模式为已解决 (INFRA-189) ([#475](https://github.com/hdot123/memory/issues/475)) ([6882c18](https://github.com/hdot123/memory/commit/6882c18c69dd09540b97ed94a09d9a189f4d3f61))

## [0.19.0](https://github.com/hdot123/memory/compare/v0.18.7...v0.19.0) (2026-08-11)


### Features

* evolution scanner 跳过已解决错误模式增强 (INFRA-186) ([#472](https://github.com/hdot123/memory/issues/472)) ([dd805ad](https://github.com/hdot123/memory/commit/dd805ad3218d046d5a694bca622c930273528c54))

## [0.18.7](https://github.com/hdot123/memory/compare/v0.18.6...v0.18.7) (2026-08-11)


### Documentation

* 纠正 Linear/GitHub 职责约定的文档漂移 (INFRA-182) ([#467](https://github.com/hdot123/memory/issues/467)) ([61f1354](https://github.com/hdot123/memory/commit/61f13542b7a62def907fcbd6e53641bba1f93393))

## [0.18.6](https://github.com/hdot123/memory/compare/v0.18.5...v0.18.6) (2026-08-11)


### Bug Fixes

* evolution scanner 跳过已解决的错误模式 (INFRA-184) ([#469](https://github.com/hdot123/memory/issues/469)) ([f5cee9d](https://github.com/hdot123/memory/commit/f5cee9d1674d11f01af13bf2e8b4963ce4b311d7))

## [0.18.5](https://github.com/hdot123/memory/compare/v0.18.4...v0.18.5) (2026-08-11)


### Bug Fixes

* auto_close_resolved 增加 failed_categories 保护 (INFRA-176) ([#464](https://github.com/hdot123/memory/issues/464)) ([7aeb2a3](https://github.com/hdot123/memory/commit/7aeb2a3fbadb5c27f2ed037b6f0bf41d31fc3878))

## [0.18.4](https://github.com/hdot123/memory/compare/v0.18.3...v0.18.4) (2026-08-11)


### Bug Fixes

* 纠正 Linear/GitHub 职责约定的文档漂移 ([#462](https://github.com/hdot123/memory/issues/462)) ([5729856](https://github.com/hdot123/memory/commit/5729856f7f2d590f7728b5f03dd1ab7a27e12457))

## [0.18.3](https://github.com/hdot123/memory/compare/v0.18.2...v0.18.3) (2026-08-11)


### Bug Fixes

* GAP-G 调整 auto_close_resolved 执行顺序到 P2-A 检查之后 (INFRA-172) ([#461](https://github.com/hdot123/memory/issues/461)) ([3035280](https://github.com/hdot123/memory/commit/30352808532f1e95a844462a1a2f9705d8c4851d))

## [0.18.2](https://github.com/hdot123/memory/compare/v0.18.1...v0.18.2) (2026-08-11)


### Bug Fixes

* transcript_missing 不再记录为错误 (INFRA-164) ([#452](https://github.com/hdot123/memory/issues/452)) ([209dc02](https://github.com/hdot123/memory/commit/209dc02e4bb6f69a7ceb38c5f936c46e980f063a))

## [0.18.1](https://github.com/hdot123/memory/compare/v0.18.0...v0.18.1) (2026-08-11)


### Documentation

* 在 README 中补充已解决 Issues 自动关闭机制说明 ([#449](https://github.com/hdot123/memory/issues/449)) ([8dff7a5](https://github.com/hdot123/memory/commit/8dff7a55308aa10d25061561b127e6ed324b6ec5))

## [0.18.0](https://github.com/hdot123/memory/compare/v0.17.0...v0.18.0) (2026-08-11)


### Features

* 添加已解决 Issues 自动关闭机制及文档更新 ([#447](https://github.com/hdot123/memory/issues/447)) ([3313974](https://github.com/hdot123/memory/commit/33139744e37794b48dffd23f830b3f3d1ec61e68))

## [0.17.0](https://github.com/hdot123/memory/compare/v0.16.6...v0.17.0) (2026-08-11)


### Features

* **docs:** GitHub↔Linear Issue 流转约定文档 + Scanner 模板增强 ([#445](https://github.com/hdot123/memory/issues/445)) ([e22d9dd](https://github.com/hdot123/memory/commit/e22d9ddc235c532c2a8803b1128033fca03e54b1))

## [0.16.6](https://github.com/hdot123/memory/compare/v0.16.5...v0.16.6) (2026-08-10)


### Bug Fixes

* **evolution:** 用时效性检查替换 findings 数量阈值，修复 EVOLUTION_FINDINGS_INSUFFICIENT 误报 ([#442](https://github.com/hdot123/memory/issues/442)) ([e0a4edf](https://github.com/hdot123/memory/commit/e0a4edfcd77fc120bbab1947b775c8c2437a5553))

## [0.16.5](https://github.com/hdot123/memory/compare/v0.16.4...v0.16.5) (2026-08-10)


### Bug Fixes

* **evolution:** [INFRA-154] 修复 check_findings_over_time 读取错误的 JSON 键导致 EVOLUTION_FINDINGS_INSUFFICIENT 永远误报 ([#436](https://github.com/hdot123/memory/issues/436)) ([f454590](https://github.com/hdot123/memory/commit/f4545901eadaf2dc06fba6fc39a9710e348cc307))

## [0.16.4](https://github.com/hdot123/memory/compare/v0.16.3...v0.16.4) (2026-08-10)


### Bug Fixes

* 移除 droid-wiki/Ownership-Model.md 的 git 追踪（.gitignore 已覆盖但未 rm --cached） ([#437](https://github.com/hdot123/memory/issues/437)) ([828f62a](https://github.com/hdot123/memory/commit/828f62ac0f0e3c30c0bb25339734d360c15abc79))

## [0.16.3](https://github.com/hdot123/memory/compare/v0.16.2...v0.16.3) (2026-08-10)


### Bug Fixes

* **evolution:** [INFRA-150] 移除 EVOLUTION_SUPPRESS_EMPTY 误报规则 ([#433](https://github.com/hdot123/memory/issues/433)) ([05f7ad0](https://github.com/hdot123/memory/commit/05f7ad0e019438aefa8974bb500d4c4dc8f0acc3))
* **guard:** [INFRA-149] pretooluse_guard 改为按 Unicode 类别剥离全部 Cc/Cf 不可见字符 ([#429](https://github.com/hdot123/memory/issues/429)) ([6f0436d](https://github.com/hdot123/memory/commit/6f0436df2f1e9f4d798979c63677f1303f8fcad4))

## [0.16.2](https://github.com/hdot123/memory/compare/v0.16.1...v0.16.2) (2026-08-10)


### Bug Fixes

* **evolution:** 修复审计工具缺少--target参数，新增工具健康检查 ([#430](https://github.com/hdot123/memory/issues/430)) ([0b21c95](https://github.com/hdot123/memory/commit/0b21c95ea971ef7fa56192d676d896c09dd9fec9))

## [0.16.1](https://github.com/hdot123/memory/compare/v0.16.0...v0.16.1) (2026-08-10)


### Bug Fixes

* **guard:** [INFRA-145] 修复 pretooluse_guard 零宽字符/多重BOM stdin 触发 json_parse_error 误报 ([#425](https://github.com/hdot123/memory/issues/425)) ([8aefdd0](https://github.com/hdot123/memory/commit/8aefdd04f446ea57db2fe355f0d40bb7535381b3))

## [0.16.0](https://github.com/hdot123/memory/compare/v0.15.32...v0.16.0) (2026-08-10)


### Features

* **evolution:** 扩展审计工具至6个，新增 evolution_self_audit 自检工具 ([#414](https://github.com/hdot123/memory/issues/414)) ([e250b0e](https://github.com/hdot123/memory/commit/e250b0e1df6b481744f25f1803383996b1ffbca0))

## [0.15.32](https://github.com/hdot123/memory/compare/v0.15.31...v0.15.32) (2026-08-10)


### Bug Fixes

* **guard:** [INFRA-143] 修复 pretooluse_guard BOM/空字节 stdin 触发 json_parse_error 误报 ([#423](https://github.com/hdot123/memory/issues/423)) ([c8c0b4f](https://github.com/hdot123/memory/commit/c8c0b4fe7a790dfb585c6a7b70f13ea5db718a39))

## [0.15.31](https://github.com/hdot123/memory/compare/v0.15.30...v0.15.31) (2026-08-10)


### Bug Fixes

* **guard:** [INFRA-141] 修复 pretooluse_guard 空 stdin/IO 异常误报 json_parse_error ([#419](https://github.com/hdot123/memory/issues/419)) ([5ca1b60](https://github.com/hdot123/memory/commit/5ca1b60cfdf7387708d61b5fbab4eabfc29aaf8e))

## [0.15.30](https://github.com/hdot123/memory/compare/v0.15.29...v0.15.30) (2026-08-10)


### Bug Fixes

* **evolution:** [INFRA-139] 修复 normalize_location 的 lstrip 字符集缺陷 ([#417](https://github.com/hdot123/memory/issues/417)) ([ad46e3e](https://github.com/hdot123/memory/commit/ad46e3ead4e35a170aad469bec5ba3c90ed59a2b))

## [0.15.29](https://github.com/hdot123/memory/compare/v0.15.28...v0.15.29) (2026-08-10)


### Bug Fixes

* **guard:** [INFRA-138] 修复 pretooluse_guard 空 stdin 触发 json_parse_error 误报 ([#415](https://github.com/hdot123/memory/issues/415)) ([7dd35cc](https://github.com/hdot123/memory/commit/7dd35cc49a119397c38a509c01eb3f90b5d47bbb))

## [0.15.28](https://github.com/hdot123/memory/compare/v0.15.27...v0.15.28) (2026-08-10)


### Bug Fixes

* **evolution:** 修复 scanner 结构性缺陷和 adapter location 规范化 ([#412](https://github.com/hdot123/memory/issues/412)) ([31e3a88](https://github.com/hdot123/memory/commit/31e3a88e05f52767a59a4fbf89e8f6f9f8f4609f))

## [0.15.27](https://github.com/hdot123/memory/compare/v0.15.26...v0.15.27) (2026-08-10)


### Bug Fixes

* **evolution:** [INFRA-95] 修复 init_validate_roundtrip 误报 CONSISTENCY_ERROR ([#408](https://github.com/hdot123/memory/issues/408)) ([95b5faa](https://github.com/hdot123/memory/commit/95b5faa388a54bee0687a79e5ffae5e2e4de4f4f))

## [0.15.26](https://github.com/hdot123/memory/compare/v0.15.25...v0.15.26) (2026-08-10)


### Bug Fixes

* **evolution:** [INFRA-129] 错误模式检测器过滤测试产物防止误报 ([#400](https://github.com/hdot123/memory/issues/400)) ([7a3d35b](https://github.com/hdot123/memory/commit/7a3d35b35d85ec564d38823109441ef1be3283ee))
* **evolution:** [INFRA-96] 修复 test_hook_event.py docstring 缺少 factory 提及 ([#406](https://github.com/hdot123/memory/issues/406)) ([6b4bdaa](https://github.com/hdot123/memory/commit/6b4bdaaed57c7a12f32e04533f29914950f89f49))


### Documentation

* **test:** [INFRA-98] 修复 test_memory_hook_gateway_coverage.py 文档字符串主机提及一致性 ([#404](https://github.com/hdot123/memory/issues/404)) ([b53e96d](https://github.com/hdot123/memory/commit/b53e96d790e093036e5b34f839faff6797a9ffc1))
* **test:** [INFRA-99] 修复 test_init_completeness.py 文档字符串主机提及一致性 ([#403](https://github.com/hdot123/memory/issues/403)) ([6d8c1ca](https://github.com/hdot123/memory/commit/6d8c1ca8cb84c67b2315c4ea3361f4fe58cc7b01))

## [0.15.25](https://github.com/hdot123/memory/compare/v0.15.24...v0.15.25) (2026-08-10)


### Bug Fixes

* **evolution:** [INFRA-100] 修复 test_dispatch_output_package 文档字符串主机引用不一致 ([#401](https://github.com/hdot123/memory/issues/401)) ([0f76ba4](https://github.com/hdot123/memory/commit/0f76ba49c8ba271d2ffc3bf4573ae5ba42d307fb))

## [0.15.24](https://github.com/hdot123/memory/compare/v0.15.23...v0.15.24) (2026-08-10)


### Bug Fixes

* **evolution:** [INFRA-102] 修复 memory_hook_impls 模块文档字符串主机引用不一致 ([#398](https://github.com/hdot123/memory/issues/398)) ([bdfc68e](https://github.com/hdot123/memory/commit/bdfc68e63482ec2899034f80ca84bbf555ad608b))

## [0.15.23](https://github.com/hdot123/memory/compare/v0.15.22...v0.15.23) (2026-08-10)


### Bug Fixes

* **evolution:** [INFRA-103] 修复 validate_project_memory 文档字符串主机引用不一致 ([#396](https://github.com/hdot123/memory/issues/396)) ([f7889f1](https://github.com/hdot123/memory/commit/f7889f19dda50cd0bbf344c74e71151acfa879b2))
* **evolution:** [INFRA-118] 将 status_enum 校验接入 validate_project_memory ([#384](https://github.com/hdot123/memory/issues/384)) ([cf11419](https://github.com/hdot123/memory/commit/cf114196c5e9bc2c54fa5dc1dba7aeadb55d9a48))
* **validator:** [INFRA-106] _parse_lock_file 改为严格 TOML 解析 ([#392](https://github.com/hdot123/memory/issues/392)) ([d3d663a](https://github.com/hdot123/memory/commit/d3d663a629034f0c99a998951d15346aeaf98ff3))

## [0.15.22](https://github.com/hdot123/memory/compare/v0.15.21...v0.15.22) (2026-08-10)


### Bug Fixes

* **consistency:** [INFRA-104] init_project_memory docstring 补全 factory 主机引用并修正 host 默认值 ([#394](https://github.com/hdot123/memory/issues/394)) ([2b1b8af](https://github.com/hdot123/memory/commit/2b1b8af1e55d05ac856da8b8b4db0a067ff37ca5))
* **evolution:** [INFRA-125] 修复审计适配器静默失效 ([#393](https://github.com/hdot123/memory/issues/393)) ([e28b01b](https://github.com/hdot123/memory/commit/e28b01b33a4300652c3b4dd6dfd490e2915e22f8))

## [0.15.21](https://github.com/hdot123/memory/compare/v0.15.20...v0.15.21) (2026-08-10)


### Documentation

* [INFRA-109] 清理 MEMORY_LOCK_SPEC 中的旧版本 0.1.0 引用 ([#389](https://github.com/hdot123/memory/issues/389)) ([8d78a3d](https://github.com/hdot123/memory/commit/8d78a3d7f8d3bb0abd4fd53a801ae36d50b65bbf))

## [0.15.20](https://github.com/hdot123/memory/compare/v0.15.19...v0.15.20) (2026-08-10)


### Bug Fixes

* **docs:** 清除 10-consumer-boundary.md 过期版本引用 ([#386](https://github.com/hdot123/memory/issues/386)) ([c74854e](https://github.com/hdot123/memory/commit/c74854ecba6f27ffc389244b45ff1911a8bbdbc4))

## [0.15.19](https://github.com/hdot123/memory/compare/v0.15.18...v0.15.19) (2026-08-10)


### Documentation

* 更新 release-guide 版本影响列表述避免版本引用误报（INFRA-117） ([#385](https://github.com/hdot123/memory/issues/385)) ([bb2068b](https://github.com/hdot123/memory/commit/bb2068b7dee03c410308d9fc6d5fbffb3150a4ef))

## [0.15.18](https://github.com/hdot123/memory/compare/v0.15.17...v0.15.18) (2026-08-10)


### Bug Fixes

* **evolution:** [INFRA-122] adapter 去重 + 吞吐修复 + 清理死文本 ([#382](https://github.com/hdot123/memory/issues/382)) ([48a063a](https://github.com/hdot123/memory/commit/48a063a1b28b1e78b1f57a1d52267dfea4096d3e))

## [0.15.17](https://github.com/hdot123/memory/compare/v0.15.16...v0.15.17) (2026-08-10)


### Bug Fixes

* **evolution:** [INFRA-122] 修复 CONTRIBUTING_VERSION_SOURCE 持续误报 ([#380](https://github.com/hdot123/memory/issues/380)) ([67ced14](https://github.com/hdot123/memory/commit/67ced14e06dcc62d915df773118e31ea41e4f7f1))

## [0.15.16](https://github.com/hdot123/memory/compare/v0.15.15...v0.15.16) (2026-08-10)


### Bug Fixes

* **evolution:** [INFRA-121] 修复 CONTRIBUTING_VERSION_SOURCE 持续误报 ([#377](https://github.com/hdot123/memory/issues/377)) ([52b25d3](https://github.com/hdot123/memory/commit/52b25d3b77faab570984231e342b7155204c4c27))

## [0.15.15](https://github.com/hdot123/memory/compare/v0.15.14...v0.15.15) (2026-08-10)


### Bug Fixes

* **evolution:** [INFRA-110] 修复 CONTRIBUTING_VERSION_SOURCE 误报 ([#367](https://github.com/hdot123/memory/issues/367)) ([a003eb8](https://github.com/hdot123/memory/commit/a003eb83f65b22cde46a7957082989e83b08c63c))

## [0.15.14](https://github.com/hdot123/memory/compare/v0.15.13...v0.15.14) (2026-08-10)


### Bug Fixes

* **docs:** 清除文档中过期的 wb-hook-v2 schema 引用 ([#371](https://github.com/hdot123/memory/issues/371)) ([b645495](https://github.com/hdot123/memory/commit/b6454952f5558e506a99b0dd8bdc9f67cbaabf13))

## [0.15.13](https://github.com/hdot123/memory/compare/v0.15.12...v0.15.13) (2026-08-10)


### Bug Fixes

* **evolution:** INFRA-92 加固进化扫描器 CI ([#347](https://github.com/hdot123/memory/issues/347)) ([835dce9](https://github.com/hdot123/memory/commit/835dce92b485259048bbc0a04c913d2a5b01e0de))
* **evolution:** P1-A 模块投毒防护 + P2-A API 失败退出 + P2-B token 隔离 ([#346](https://github.com/hdot123/memory/issues/346)) ([be8341a](https://github.com/hdot123/memory/commit/be8341a504c2c2f31804fac932274d4ea195a807))


### Documentation

* [INFRA-105] 修正 CONTRIBUTING.md 版本号来源说明（CONTRIBUTING_VERSION_SOURCE）([#359](https://github.com/hdot123/memory/issues/359)) ([f0e41c5](https://github.com/hdot123/memory/commit/f0e41c592f8fe9905bc595f55447d7bb157d4b2c))

## [0.15.12](https://github.com/hdot123/memory/compare/v0.15.11...v0.15.12) (2026-08-09)


### Bug Fixes

* **evolution:** P1 labels bootstrap + exit code + P2 深度校验 + 重命名防护 ([#341](https://github.com/hdot123/memory/issues/341)) ([16a9b96](https://github.com/hdot123/memory/commit/16a9b96b240bf31e7b2fb003ac378a498ca161bd))

## [0.15.11](https://github.com/hdot123/memory/compare/v0.15.10...v0.15.11) (2026-08-09)


### Bug Fixes

* **evolution:** Opus 5 审计上层修复 — 扫描器核心、适配器消毒、治理 CI ([#335](https://github.com/hdot123/memory/issues/335)) ([42a2120](https://github.com/hdot123/memory/commit/42a2120391b2551c4affcd523c686ff248bcd64d))
* **evolution:** 修复剩余 P2/P3 审计发现 ([#339](https://github.com/hdot123/memory/issues/339)) ([12d2f78](https://github.com/hdot123/memory/commit/12d2f789cb49ebec397ca155fd1f63c26e87d303))
* **evolution:** 修复治理 CI P1-1/P2-1/P2-3 审计发现 ([#337](https://github.com/hdot123/memory/issues/337)) ([13ae087](https://github.com/hdot123/memory/commit/13ae0878ddb9a362271a2f58cc23c7317fa4094a))
* **governance:** 修正 owner 用户名 busiji → hdot123 ([#338](https://github.com/hdot123/memory/issues/338)) ([c6f824d](https://github.com/hdot123/memory/commit/c6f824d7fe12deea4709bec27e99d7c2e528c0cd))

## [0.15.10](https://github.com/hdot123/memory/compare/v0.15.9...v0.15.10) (2026-08-09)


### Bug Fixes

* **evolution:** 修复进化扫描器稳定性与正确性缺陷 (INFRA-81) ([#331](https://github.com/hdot123/memory/issues/331)) ([4e4c14e](https://github.com/hdot123/memory/commit/4e4c14effb5bf22fb0d15b8c9ad304ace7c62c6b))

## [0.15.9](https://github.com/hdot123/memory/compare/v0.15.8...v0.15.9) (2026-08-09)


### Bug Fixes

* **security:** 修复 droid-review P1 审查发现（checkout ref + check过滤 + deploy脚本加固） ([#332](https://github.com/hdot123/memory/issues/332)) ([60ca129](https://github.com/hdot123/memory/commit/60ca129264ad3641108a51fb21b0ef74b306e7c9))

## [0.15.8](https://github.com/hdot123/memory/compare/v0.15.7...v0.15.8) (2026-08-09)


### Bug Fixes

* **security:** 四层纵深防御架构 — 消除3个现有安全漏洞 + 全链路安全门禁 ([#329](https://github.com/hdot123/memory/issues/329)) ([270844d](https://github.com/hdot123/memory/commit/270844d04b89a243904c56e17e435abc05ed0cb1))
* 修复 8 个 P2 审计发现（bidi字符+隔离碰撞+异常吞没+shlex+懒加载+副作用） ([#328](https://github.com/hdot123/memory/issues/328)) ([1f9d804](https://github.com/hdot123/memory/commit/1f9d804d572f3a8eb13304b78a1761528ef3cc9f))
* 修复进化扫描器 16 个缺陷（安全加固+健壮性+正确性） ([#326](https://github.com/hdot123/memory/issues/326)) ([5560c5c](https://github.com/hdot123/memory/commit/5560c5c64739acda3f157912877109b89e2f8b84))

## [0.15.7](https://github.com/hdot123/memory/compare/v0.15.6...v0.15.7) (2026-08-07)


### Bug Fixes

* **kb:** 补充全量 Truth Basis 覆盖，消除知识库验证死角 ([#323](https://github.com/hdot123/memory/issues/323)) ([47e306d](https://github.com/hdot123/memory/commit/47e306daa3ba413d41a8f11254fd29913749a97c))
* 根治 SessionEnd hook SIGINT 崩溃，增强日志和 git 操作健壮性 ([#324](https://github.com/hdot123/memory/issues/324)) ([bddb4a5](https://github.com/hdot123/memory/commit/bddb4a5d427c12961f712ee0c92f17fb0fa8adc6))

## [0.15.6](https://github.com/hdot123/memory/compare/v0.15.5...v0.15.6) (2026-08-06)


### Documentation

* 修正发版文档漂移，补充 upgrade-consumer 流程描述 ([#314](https://github.com/hdot123/memory/issues/314)) ([3b76c8c](https://github.com/hdot123/memory/commit/3b76c8c098f0de7b88f8e8fb8efd5c9c5979a0ae))

## [0.15.5](https://github.com/hdot123/memory/compare/v0.15.4...v0.15.5) (2026-08-06)


### Bug Fixes

* 填充全局规范文件并创建 KB 格式规范 ([#319](https://github.com/hdot123/memory/issues/319)) ([678aafa](https://github.com/hdot123/memory/commit/678aafabe81a442a242b8791c649a9d8be197582))

## [0.15.4](https://github.com/hdot123/memory/compare/v0.15.3...v0.15.4) (2026-08-06)


### Bug Fixes

* 修复 lesson 幽灵引用、缺失 Truth Basis 和格式问题 ([#317](https://github.com/hdot123/memory/issues/317)) ([f80a18f](https://github.com/hdot123/memory/commit/f80a18f5f00809c97e51313c5599561b7065b3be))

## [0.15.3](https://github.com/hdot123/memory/compare/v0.15.2...v0.15.3) (2026-08-06)


### Bug Fixes

* 创建 memory_core.md 项目规范并修复 INDEX.md 幻影条目 ([#315](https://github.com/hdot123/memory/issues/315)) ([231cdc6](https://github.com/hdot123/memory/commit/231cdc6449926f3128046bdc17c2fb21439a7d40))

## [0.15.2](https://github.com/hdot123/memory/compare/v0.15.1...v0.15.2) (2026-08-06)


### Documentation

* 修正文档索引引用并清理 lesson 失效 refs (INFRA-69) ([4a97828](https://github.com/hdot123/memory/commit/4a978282f19af9f5fd8fe3b779be8b120111d12b))

## [0.15.1](https://github.com/hdot123/memory/compare/v0.15.0...v0.15.1) (2026-08-06)


### Bug Fixes

* 补全基础层缺失的 project-map/global canonical 文件及 CI 守卫适配 ([#310](https://github.com/hdot123/memory/issues/310)) ([76c2e28](https://github.com/hdot123/memory/commit/76c2e28fab0f415e1fe53ae4562fbbeda402b500))

## [0.15.0](https://github.com/hdot123/memory/compare/v0.14.0...v0.15.0) (2026-08-05)


### Features

* stub添加定时扫描+workflow_dispatch兜底重试机制 ([9afa8c2](https://github.com/hdot123/memory/commit/9afa8c22b5fe212b86c8a934216ffdff17a314fe))


### Bug Fixes

* pull_request改为pull_request_target，修复bot触发被action_required拦截 ([79b3bc5](https://github.com/hdot123/memory/commit/79b3bc5df18be4ddf7970a1fd8136f785925570a))

## [0.14.0](https://github.com/hdot123/memory/compare/v0.13.4...v0.14.0) (2026-08-05)


### Features

* 添加 dependabot 配置，启用 auto-merge 自动合并 ([#305](https://github.com/hdot123/memory/issues/305)) ([128d14c](https://github.com/hdot123/memory/commit/128d14cdf25c9fa9ecf9a2b2f50ff9adc67399ad))

## [0.13.4](https://github.com/hdot123/memory/compare/v0.13.3...v0.13.4) (2026-08-05)


### Bug Fixes

* 创建 auto-merge workflow，接入 shared-workflows 引擎 ([#306](https://github.com/hdot123/memory/issues/306)) ([3a501e7](https://github.com/hdot123/memory/commit/3a501e788ef83e445c5c33a48961989a0d667586))

## [0.13.3](https://github.com/hdot123/memory/compare/v0.13.2...v0.13.3) (2026-08-05)


### Bug Fixes

* 根治 SessionEnd hook SIGINT 崩溃 ([#300](https://github.com/hdot123/memory/issues/300)) ([1ffe055](https://github.com/hdot123/memory/commit/1ffe055ca6eb01333ce38b82c320c9a6a77b2c0c))

## [0.13.2](https://github.com/hdot123/memory/compare/v0.13.1...v0.13.2) (2026-08-04)


### Bug Fixes

* upgrade-consumer 添加 --break-system-packages 修复 PEP 668 限制 ([#297](https://github.com/hdot123/memory/issues/297)) ([76c63cb](https://github.com/hdot123/memory/commit/76c63cb1837fee73d522d9ceac86ef1c069574aa))

## [0.13.1](https://github.com/hdot123/memory/compare/v0.13.0...v0.13.1) (2026-08-04)


### Bug Fixes

* 修复 upgrade-consumer 使用错误 Python 路径，修复 workflow_dispatch 发版失败 ([#295](https://github.com/hdot123/memory/issues/295)) ([2bbdb3d](https://github.com/hdot123/memory/commit/2bbdb3dd0c9f498740b919e661c51ba0daa6e02c))

## [0.13.0](https://github.com/hdot123/memory/compare/v0.12.0...v0.13.0) (2026-08-04)


### Features

* 发版后自动升级 Mac 全局 memory-core 安装 ([#293](https://github.com/hdot123/memory/issues/293)) ([4bfc42f](https://github.com/hdot123/memory/commit/4bfc42f4d2712d815430305e56082bad21fdde92))

## [0.12.0](https://github.com/hdot123/memory/compare/v0.11.1...v0.12.0) (2026-08-04)


### Features

* release-please 启用 automerge，CI 通过后自动合并 ([#291](https://github.com/hdot123/memory/issues/291)) ([4671873](https://github.com/hdot123/memory/commit/467187320ab9eda2a1678aef0bf1d0c6476de211))

## [0.11.1](https://github.com/hdot123/memory/compare/v0.11.0...v0.11.1) (2026-08-04)


### Bug Fixes

* 修复 branch-cleanup.yml 安全性问题 ([#289](https://github.com/hdot123/memory/issues/289)) ([fec5c85](https://github.com/hdot123/memory/commit/fec5c857b2f4d31fd4fdacc1be2b9d0ff2655069))

## [0.11.0](https://github.com/hdot123/memory/compare/v0.10.1...v0.11.0) (2026-08-04)


### Features

* 添加自动清理孤立分支的 GitHub Actions workflow ([#286](https://github.com/hdot123/memory/issues/286)) ([7609869](https://github.com/hdot123/memory/commit/76098691b87f0601956580f4b865cafdd69d5100))

## [0.10.1](https://github.com/hdot123/memory/compare/v0.10.0...v0.10.1) (2026-08-04)


### Bug Fixes

* release-please 使用 DISPATCH_TOKEN 触发下游 workflow ([#284](https://github.com/hdot123/memory/issues/284)) ([221040d](https://github.com/hdot123/memory/commit/221040d9ce807a56f7d7d6417d9e7587852a41c0))

## [0.10.0](https://github.com/hdot123/memory/compare/v0.9.5...v0.10.0) (2026-08-04)


### Features

* 引入 release-please 自动化版本管理 ([#270](https://github.com/hdot123/memory/issues/270)) ([95d80a0](https://github.com/hdot123/memory/commit/95d80a0d98679f07647b506d4b415c0d86faeee8))
* 引入 release-please 自动化版本管理 ([#273](https://github.com/hdot123/memory/issues/273)) ([b1f7109](https://github.com/hdot123/memory/commit/b1f7109c8b679c3ac71d7048a0c0fe01a709eaae))


### Bug Fixes

* 为 README.md 添加 x-release-please-version 注解 ([#283](https://github.com/hdot123/memory/issues/283)) ([4e8a910](https://github.com/hdot123/memory/commit/4e8a910183f63e360fe0cbf09242cdbe17057b52))
* 修正 release-please extra-files 配置，README.md 使用 rewrite 类型 ([#280](https://github.com/hdot123/memory/issues/280)) ([1cd1bd5](https://github.com/hdot123/memory/commit/1cd1bd55c9a0febce77e8d3de57fc3d4d3aa6cd3))
* 修正 release-please extra-files 配置，移除 type: rewrite ([#282](https://github.com/hdot123/memory/issues/282)) ([2898aa9](https://github.com/hdot123/memory/commit/2898aa969355a82b1720afe3df57077a3ed565d1))
* 修正 release-please manifest 格式，添加 tag 推送触发器 ([#276](https://github.com/hdot123/memory/issues/276)) ([853ce83](https://github.com/hdot123/memory/commit/853ce830bf4d0ae43f8a71cd1bee9bc9d72b9beb))
* 暴露 __version__ 让 release-please 原生 bump 版本号 ([#278](https://github.com/hdot123/memory/issues/278)) ([f4e0e54](https://github.com/hdot123/memory/commit/f4e0e54299f8e1d0e43e62b7e39d29b31b22dd78))


### Documentation

* 发布流程文档全面更新，对齐 release-please 自动化 ([#271](https://github.com/hdot123/memory/issues/271)) ([3c61440](https://github.com/hdot123/memory/commit/3c614406b8cb509016157f570d3605b26f592a14))
* 更新发版流程文档对齐 release-please 自动化 (INFRA-37) ([#277](https://github.com/hdot123/memory/issues/277)) ([007658a](https://github.com/hdot123/memory/commit/007658acf6764a6049bc51aaace114dc12002c9a))
* 标准化发版流程文档，引入 release-please 自动化 ([#274](https://github.com/hdot123/memory/issues/274)) ([09ad703](https://github.com/hdot123/memory/commit/09ad7031074c0d7454a09e21fe59217a588df170))

## [0.9.5] - 2026-08-04

### Added
- **release-please 自动化版本管理**：引入 [release-please](https://github.com/googleapis/release-please) 自动管理版本号、CHANGELOG 和 GitHub Release。基于 Conventional Commits 自动判定版本级别（patch/minor/major）。
- **发版流程文档**：新增 `docs/guides/release-guide.md` 发版指南，覆盖自动发版、手动发版、回滚、下游通知全流程。

### Changed
- **版本号一致性**：pyproject.toml、constants.py、README.md 统一为 0.9.5
- **测试版本号读取**：测试文件通过 `CURRENT_MEMORY_VERSION` 动态读取版本号，消除硬编码

### Notes
- release-please 使用 `packages` 模式，manifest 格式为 `{"\u002e": "X.Y.Z"}`
- `release-and-dispatch.yml` 支持 tag 推送触发（`push: tags: [v*]`）和手动触发（`workflow_dispatch`）

## [0.9.4] - 2026-08-01

### Added
- **生命周期事件按项目分片存储**：从全局 `events.jsonl` 迁移到 `projects/{project_id}/events/{YYYY-MM-DD}.jsonl` 结构，支持按项目和日期隔离事件，便于归档和清理。
- **自动清理机制**：新增 `_cleanup_old_event_files()` 函数，通过 `MEMORY_HOOK_LIFECYCLE_RETENTION_DAYS` 环境变量配置保留天数（默认 30 天，设为 0 禁用），每个项目每天最多清理一次。
- **迁移 CLI 工具**：`memory-lifecycle-migrate` 命令将旧的 `events.jsonl` 迁移到新的分片结构，支持幂等运行、自动归档原文件、输出统计信息。
- **向后兼容性测试**：新增 VAL-COMPAT-01~04 和 VAL-CROSS-01~03 测试，验证 `rebuild_path_index()`、`build_project_lifecycle_record()`、`hook_event_stats.py` 不受影响，以及完整生命周期原子性、迁移后写入连续性、并发项目隔离。

### Changed
- **生命周期事件写入路径**：`record_project_lifecycle()` 现在写入 `projects/{project_id}/events/{YYYY-MM-DD}.jsonl` 而非全局 `events.jsonl`。返回字典的 `event_log` 字段指向新路径。
- **文档更新**：HOOK_INTEGRATION_SPEC.md 新增第 9 章，说明新的事件存储结构、写入路径、自动清理、迁移工具和向后兼容性。

### Fixed
- **迁移健壮性**：非对象 JSON 行（如 `123`、`[1,2]`）不再崩溃，通过 `isinstance(event_data, dict)` 守卫优雅跳过 (PR #232)。
- **迁移统计准确性**：空行计入 `skipped` 计数器，确保 `written + skipped == total_read` 对账成立 (PR #232)。
- **清理日志可见性**：`_cleanup_old_event_files()` 和 `record_project_lifecycle()` 中的清理异常现在发出 `warnings.warn()` 而非静默吞掉 (PR #232)。
- **retention 环境变量容错**：非整数 `MEMORY_HOOK_LIFECYCLE_RETENTION_DAYS` 值回退到默认 30，不再静默禁用清理 (PR #232)。
- **版本一致性**：0.9.3 → 0.9.4 全量同步（constants.py、compat.py、README.md、全部 test fixtures） (PR #232)。

### Notes
- 全局 `events.jsonl` 已弃用但不会被删除，可通过 `memory-lifecycle-migrate` 迁移并归档为 `events.jsonl.archived`
- 所有现有测试通过，无破坏性变更

## [0.9.3] - 2026-08-01

### Changed
- **Hook 性能优化**：非注入事件（stop、notification、subagent-stop、post-tool-use、pre-compact、session-end）实现快速路径，跳过 `build_context_package()` 和 artifact snapshot 写入，仅保留生命周期记录、metrics 和轻量审计日志。预期减少 90% 文件读取、60% git 子进程、50% 文件写入。注入事件（session-start、prompt-submit）行为不变 (PR #229)。

### Fixed
- `_try_resign_ownership` silent exception swallowing: expanded to `_try_resign_all`, which now reports errors instead of `except: pass`.
- `path-index.json` divergence from the `projects/` directory: no rebuild mechanism existed before; `memory-lifecycle-rebuild` closes this gap.
- 非注入事件（stop/notification/session-end）输出抑制：成功时返回 `{"suppressOutput": true}` 避免终端空输出干扰，降级状态仍返回 `{}` 保持错误可见 (PR #227)。

## [0.9.1] - 2026-07-24

### Fixed
- **SessionEnd hook SIGALRM boot-timeout 保护**: 修复 SessionEnd hook 在系统高负载时 import 超时被 Factory SIGINT 强杀的问题。添加 8 秒 SIGALRM boot-timeout 保护，让脚本在 Factory 10 秒 SIGINT 强杀前自行干净退出（exit 0）

## [0.9.0] - 2026-07-14

### Added
- **仓库交付一致性健康检查脚本** (`scripts/repo_health_check.sh`): 检查仓库交付质量，纳入 CI 门禁
- **集成测试纳入 CI**: 全量集成测试作为 CI 步骤运行
- **双门禁验证**: ci-ok + droid-review 双门禁流程完善
- **单元测试补充**: daily_summary_generator 覆盖率 20%→89%, daily_kb_audit 覆盖率 18%→75%
- **truth-basis 验证逻辑测试**: 完整性验证覆盖
- **advisory 纳入 ci-ok 门禁**: dependency security scan + telemetry coverage audit 作为非阻塞 advisory job

### Changed
- **health check --full 模式修复 tag 发现逻辑**: 修复版本 tag 发现问题
- **遥测准确性修复**: degraded 状态 + duration_ms + observability 桥接
- **duration_ms 测试重构**: 使用 monkeypatch 替代 patch.object，增加 fallback 验证
- **CI 测试隔离修复**: ArtifactWriter mock + stat 错误路径重构 + yaml mock 修复

### Removed
- **移除 GitLab 同步功能**: 对齐文档至 GitHub PR 流程
- **移除 PyPI 发布步骤**: release workflow 简化
- **移除 pretooluse_guard 中 gitlab_api_push.py 死代码**: 脚本已删除
- **移除 CONTRIBUTING.md Release 段 GitLab 残留**: 文档对齐 GitHub 流程

### Fixed
- **release workflow 添加 pytest-cov 安装**: 修复 --cov 参数缺失致 release 失败
- **@droid 两路 model 修复**: droid_args + review_model 覆盖 exec pass + validator pass
- **@droid 交互式 exec 模型传参**: 改用 droid_args 传模型，修复 gpt-5.2 回退被封问题

### Docs
- **更新 README 版本号到 v0.9.0**: 移除 PyPI 和 GitLab MR 残留
- **SOP 改用 --auto 自动合并**: 合并方式仅 squash
- **同步 advisory 纳入门禁到流程规范**
- **重写为 GitHub PR 流程标准规范**: 完整 SOP + 架构 + 配置 + 纪律
- **云端模型锁定为 grok-4.5**: droid + droid-review
- **PR 流程改造**: CI 全量跑 + ci-ok 门禁 + droid 自动审查

## [0.8.0] - 2026-06-20

### Added
- 全局知识库层 (~/.memory/global-kb/): operations/engineering/collaboration/pending 四域
- 分层路由 fallback: adapter.toml [global_kb] 段, 项目优先 → 全局 fallback
- memory-init 自动创建全局 KB 并写入配置
- memory-migrate 0.7→0.8 迁移支持
- memory-promote CLI: 从 pending 提升到正式分类
- session-end 自动捕获候选到 pending/

### Fixed
- ssh-tailscale-pitfalls.md BOUNDARY IP 泄漏脱敏

### Docs
- 新增通用维护手册: VERSION_SYNC_RUNBOOK / MIGRATION_RUNBOOK / CONFIG_MANAGEMENT_RUNBOOK
- 现有 CI/CD 手册加环境特定声明标注
- runbooks/INDEX.md 分为通用维护手册 + 环境特定手册两类

## [0.7.0] - 2026-06-07

### 新增
- **完整性签名 `include_runtime` 参数**（VAL-P3-001~007）：`sign_project` / `sign_project_incremental` 新增 keyword-only `include_runtime: bool = False` 参数，默认不签名运行时产物（`memory/artifacts/memory-hook/`），保持 manifest 稳定
- **resign CLI `--include-runtime` 标志**：透传 `include_runtime` 到签名函数
- **审计前缀精确匹配**（VAL-P3-008~009）：`_check_manifest_includes_runtime` 从子串匹配改为前缀匹配，消除对 `memory/system/adapter.toml`、`memory/kb/global/memory-system.md`、`memory/log/*-sessions.md` 的误报
- **初始化模板补全**（VAL-P1-001~010）：
  - `legal-core-map.md` 补齐 4 个 `legal_core_markers`
  - `ingestion-registry-map.md` 补齐 8 个 `required_registry_scopes`
  - 新增 `memory/docs/记忆系统全景文档.md` 模板（含 `project-map/INDEX.md` 引用）
  - 5 个 global-canonical 文件各加 `## Truth Basis` 段（Source/Authority/Evidence/Conflict），通过 `TruthBasisResolver` 校验
  - 新增 `tests/.memory-anchor.md` 锚点文件
- **初始化行为修复**（VAL-P2-001~008）：
  - `update_agents_md` repair 模式：文件不存在时也创建
  - `_apply_auto_fill` 增强：从 `package.json` / `tsconfig.json` / `pyproject.toml` 抽取技术栈，填充占位符；未知占位符替换为 `（待补充：xxx）`
  - init 成功后调用 `audit_project_layout` 做只读体检，P1 项作为 `result["warnings"]` 输出
- **跨 phase 端到端 golden 测试**（VAL-CROSS-001~006）：
  - init → audit → sign 全链路验证
  - init update 幂等性
  - 存量项目迁移路径（旧 codex host 残留 → update → 干净）
  - audit 不报 init 产物误判
  - 单一 factory wrapper 验证
  - version bump 记录

### 变更
- **收紧 `SUPPORTED_HOSTS` 为 `("factory",)`**（VAL-P0-006）：废弃 codex 和 claude host
- **`template_adapter_toml` 固定写入 `host = "factory"`**（VAL-P0-003）：不再从 `--host` 参数插值
- **`template_agents_md_block` 改写为 host 无关 prose**（VAL-P0-002）：不嵌入 `~/.codex/` / `~/.claude/` 路径
- **`--host` argparse 入口收紧**（VAL-P0-005/007）：init 和 gateway 仅接受 `"factory"`
- **`CURRENT_MEMORY_VERSION` 升级到 `0.7.0`**

### 删除
- **`codex_global_hooks.py` / `claude_global_hooks.py`**（VAL-P4-001/002）
- **`tests/test_codex_global_hooks.py` / `tests/test_claude_global_hooks.py`**（VAL-P4-003）
- **`pyproject.toml` 中 `memory-codex-hooks` / `memory-claude-hooks` entry points**（VAL-P4-004）
- **所有 `if host == "codex"` / `elif host == "claude"` 分支**（VAL-P4-005/006）
- **`ownership.py` 中 `codex_global_hooks.py` source-repo 标记引用**（VAL-P4-007）
- **`factory_global_hooks.py` 中 codex/claude 存在性检测探针**（VAL-P4-008）
- **`hook_upgrade.py` 中 codex/claude 导入**（VAL-P4-009）

### 修复
- **init 不再生成 `hooks.json`**（VAL-P0-001）：移除 `generate_hooks_json` 调用
- **update 模式自动清理存量项目旧 host 痕迹**（VAL-P4-010/011）：
  - AGENTS.md 中 `~/.codex/bin/memory-hook` / `~/.claude/bin/memory-hook` 引用被清除
  - `.codex/hooks.json` / `.claude/hooks.json` 残留文件被删除
- **README.md / droid-wiki 文档删除 `--host codex|claude` 引用**（VAL-P4-012/013）

## [0.6.0] - 2026-06-01

### Added
- **docs/ 展示层（AutoWiki 可索引）**：新增 `docs/` 目录结构，作为 AutoWiki 扫描入口
  - `docs/INDEX.md`：全局知识文档索引
  - `docs/CLASSIFICATION.md`：文档分类决策树
  - `docs/infrastructure/servers.md`：服务器资产清单
  - `docs/infrastructure/1password-mcp.md`：1Password Connect MCP 架构
  - `docs/guides/droid-computers.md`：Droid Computer 管理指南
  - `docs/guides/byok-models.md`：自定义模型配置指南
- **AGENTS.md 文档分类规则段**：新增快速分类表，引导 Droid 写入文档时参照 `docs/CLASSIFICATION.md`
- **.gitlab-ci.yml wiki stage**：新增 `droid-wiki-refresh` job，main 分支 push 后自动触发 AutoWiki 刷新
- **Error logger 模块**（error_logger.py）：结构化错误日志，集成到 A 层 hook gateway
- **Session end logger**（session_end_logger.py）：会话结束日志记录
- **Daily summary generator**（daily_summary_generator.py）：每日摘要生成器
- **Cross-integrity integration 测试**（test_cross_integrity_integration.py）：完整性集成测试
- **Ownership 模型增强**（ownership.py）：新增路径分类 API
- **Hook gateway 增强**（memory_hook_gateway.py）：错误日志集成、增量签名机制
- **Template sync 增强**（template_sync.py）：模板同步功能增强
- **Init project memory 增强**（init_project_memory.py）：初始化流程优化

### Changed
- `memory_core/constants.py`：版本升级到 0.6.0
- `pyproject.toml`：版本升级到 0.6.0

### Removed
- `daily_session_summary.py`：功能拆分到 daily_summary_generator.py
- `sync_to_showdoc.py`：移除 ShowDoc 同步功能
- `adapter_toml_schema.py`：精简 schema 校验逻辑
- `CONTRIBUTING.md`：移除过时内容
- `audit/SUMMARY.md`：移除过时审计摘要

## [0.5.0] - 2026-05-23

### Breaking Changes
- **Two-layer architecture**: Project-level configuration moved from hidden `.memory/` to `memory/system/`. Global runtime `~/.memory-core/` remains unchanged.
- **Removed `.memory/` directory**: The hidden project protocol directory is eliminated. All config and state files now live under `memory/system/`.
- **Deleted 5 AI template files**: `CANONICAL.md`, `STATE.md`, `PLAN.md`, `TASKS.md`, `NOW.md` are no longer created or validated. These were redundant with project README/CLAUDE.md and linear/project tools.

### Added
- **`SYSTEM_DIR` constant**: New `SYSTEM_DIR = "memory/system"` in `constants.py`
- **`memory/system/kb/` and `memory/system/skills/`**: Migrated from `.memory/kb/` and `.memory/skills/`
- **`0.4.0 → 0.5.0` migration step**: `migrate_project_memory.py` supports migrating existing projects, with backup at `memory/system/backups/pre-0.5/` and rollback support
- **Idempotent migration**: Re-running `memory-migrate --from 0.4.0 --to 0.5.0` on an already-migrated project is a no-op
- **`INDEX.md` auto-generation**: `memory-init` now auto-generates INDEX.md; context-package dynamically parses, no manual maintenance needed

### Changed
- `constants.py`: Removed CANONICAL/STATE/PLAN/TASKS/NOW constants, removed FRONTMATTER_REQUIREMENTS, removed STATUS_ENUMERATIONS
- `init_project_memory.py`: All `target / ".memory"` → `target / "memory" / "system"`, removed 5 template file generators
- `memory_root_discovery.py`: Hard cutover — marker changed from `.memory` to `memory/system`, no dual detection
- `validate_project_memory.py`: Path migration, removed validation of deleted template files
- `ownership.py` + `ownership_cli.py`: Updated path declarations from `.memory/*` to `memory/system/*`
- `memory_hook_gateway.py` + `memory_hook_impls.py` + `memory_hook_integrity_manifest.py`: Path migration
- `*_global_hooks.py` × 3 (codex, claude, factory): Path migration
- 12+ other tool files: Path migration
- `workspace/templates/.memory/` → `workspace/templates/memory/system/`
- Version bumped to `0.5.0` in `constants.py` and `pyproject.toml`

### Migration Path
- New projects: `memory-init` creates `memory/system/` directly
- Existing v0.4.x projects: `memory-migrate --from 0.4.0 --to 0.5.0` with automatic backup
- Rollback: `memory-migrate --rollback` restores from backup

## [0.4.0] - 2026-05-18

### Added
- **Ownership 数据模型 + classify API**（ownership.py, 641行）：ProtectionLevel/OwnershipKind 枚举、classify_owned_path() 统一分类 API、DEFAULT_OWNERSHIP_DOMAINS 默认三域
- **Factory PreToolUse P0 写入拦截**（pretooluse_guard.py, 620行）：Write/Edit/MultiEdit/Execute/Task 六种工具拦截，Execute 命令静态解析
- **Source repo readonly context-package**（三模式 Runtime 隔离）：consumer-project / source-repo-readonly / noop 三模式，git status 和 mtime 不变
- **Integrity manifest v2 ownership-aware 签名**：签名范围从固定 canonical 改为 ownership-derived，禁止 auto re-sign
- **integrity re-sign CLI**（memory_integrity_resign.py）：专用重签名，需 reason + token/force，写 audit trail
- **子代理 ownership policy 注入**：Task 子代理自动注入 policy block + cwd 固定为 project_root
- **ownership CLI**（ownership_cli.py）：show/validate/plan-update/apply-update 四命令
- **hook 升级工具**（hook_upgrade.py）：inspect/plan-upgrade/apply-upgrade 三命令
- **memory-init ownership.toml 生成**：create/adopt/update/repair 四模式自动生成，--force 不得绕过 Ownership
- **validate/audit/apply ownership-aware 检查**：4 类检查（declaration/domain_integrity/document_paths/shared_resources）
- **兼容矩阵**（compat.py）：memory-core / ownership schema / hook schema / manifest version 兼容性检查
- **242 个新增测试**覆盖全部 M1-M6 里程碑，全量 1612 测试通过

### Changed
- Development Status 从 Beta (4) 升级为 Production/Stable (5)
- 6 个 ARCHIVED 文档归档到 docs/archive/（DISPATCH_TEMPLATE, FIXTURES_VS_REAL, MIGRATION_*）
- Lint ignore 条目从 13 条收敛到仅全局 E501/E402
- 统一 ruff 配置到 ruff.toml，删除 pyproject.toml 重复段
- CLI API 签名全部冻结（11 个入口点）
- .gitignore 补全 .ruff_cache/

### Fixed
- 修复新测试文件中的未使用 import 和未使用变量
- 修复 prompt_validator.py 和 resilient_orchestrator.py 空白行空白符问题

## [0.3.0] - 2026-05-13

### Added
- **Layout governance CLI**：新增 `memory-init --mode create|adopt|update|repair`、`memory-audit-layout`、`memory-plan-residue`、`memory-apply-residue-plan`，用于安全接入、布局审计、残留计划和低风险计划应用
- **Forbidden overwrite guard**：自动初始化/残留应用禁止覆盖业务入口 `AGENTS.md`、`INDEX.md`、`project-map/**`、`CLAUDE.md`；`adopt` 不向未标记 `AGENTS.md` 追加 hook block
- **Health Report layout_audit**：健康报告包含只读布局审计摘要，布局审计失败或 P0/P1 发现降级为 `degraded` 而非硬失败
- **L2 Integrity Layer**：SHA-256 + HMAC-SHA256 签名和验证，三个模块（keys/manifest/verify）
- **Health Report**：异步健康检查，`session-start` 时后台启动，下次注入检查结果作为 alert
- **Project Lifecycle**：多项目生命周期追踪，project_id 唯一标识，path-index 路径索引，missing 标记
- **Memory Root Discovery**：从 cwd 向上查找 `.memory/` 定位项目根，支持 monorepo sentinel
- **Thread-safe Config**：`get_config(key)` + `_config_lock` 线程安全配置访问
- **Schema `is_lossless()` API**：运行时检测 schema 转换数据丢失，审计日志写入 `schema-audit.log`
- **Adapter TOML Schema 校验**：`adapter_toml_schema.py` 结构化校验，字段类型/必填/枚举约束
- **`memory-init` 新增模板**：NOW.md、inbox.md、policy-pack.json、project-scope.md（runtime required）
- **`memory-init` L2 自动签名**：初始化后自动签名首个 manifest（best-effort）
- **Artifact 日期分区隔离**：按 project_scope 隔离 artifact 输出
- **Pollution detection whitelist** + `--check pollution` CLI（validate_memory_system）
- **CI health check script** + GitHub/GitLab integration（scripts/ci_health_check.sh）
- 新增 `memory_core/constants.py` 常量集中管理（CURRENT_MEMORY_VERSION, SUPPORTED_HOSTS 等）
- 新增 `memory_core/tools/consistency_check.py` 一致性检查工具（18 项检查）
- 新增 `factory` 主机支持（第三类宿主平台）
- 新增 `memory-consistency-check` CLI 入口点

### Changed
- **文档更新**：README.md 改为开源项目首页并补充 layout governance CLI
- **文档更新**：DOT_MEMORY_SPEC.md 补充 NOW.md/inbox.md/manifest.json/policy-pack.json 及布局治理规则
- **文档更新**：MULTI_PROJECT_SCAN_SPEC.md 状态从 ARCHIVED 改为 implemented
- memory.lock 格式从 JSON 迁移到 TOML
- 所有硬编码版本号统一引用 `constants.CURRENT_MEMORY_VERSION`
- 所有硬编码主机列表统一引用 `constants.SUPPORTED_HOSTS`
- init 项目模板全面升级（CANONICAL.md、PLAN.md、STATE.md、TASKS.md 结构化）
- default_runtime_profile 返回键从 21 个扩展到 51 个
- validate_project_memory 新增 3 项检查（state 枚举、SemVer、host 枚举）
- memory_hook_gateway adapter 加载重构为函数化
- migrations.log writes now use fcntl.flock (POSIX, Windows fail-soft)
- adapter.toml migration refactored to structured transformer registry
- workbot DeprecationWarning suppressed during pytest collection (conftest.py)

### Deprecated
- 多个 docs/ 文档标记为 ARCHIVED（DISPATCH_TEMPLATE, FIXTURES_VS_REAL, MIGRATION_* 等）

### Removed
- `CLAUDE_HOOK_STATE_DIR` dead code
- `# TODO: remove if unused` annotation on `CoreConfig.from_gateway_kwargs`

### Archived
- `memory_core/tools/ANALYSIS_GATEWAY_ADAPTER.md` → `archive/legacy-analysis/`

## [0.2.0] - 2026-04-30

### Changed
- 统一版本来源到 pyproject.toml，CLI 支持 --version
- 补齐 .gitignore，清理已追踪污染路径
- 新增 MIT LICENSE 与完整项目元数据

### Note
- 458 测试通过基线

## [0.1.0] - 2026-04-XX

### Added
- memory-init / memory-validate / memory-migrate 三大核心 CLI
- .memory/ 目录结构与版本管理能力
- adapter.toml 协议与 runtime profile 机制
- HookEvent 归一化（Codex / Claude dual-host）
- Schema 转换链（wb-hook-v2 → context-package-v1 → memory-v1）
- 污染防护（pollution guard）
- NoopHostDelegate 与 delegate resolution
- Root discovery 模块
- 项目知识目录模板（kb/）
