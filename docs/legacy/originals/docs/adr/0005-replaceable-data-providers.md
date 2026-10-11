> 历史设计资料：原仓库提交 dc53d5b3c914bf4c446809b01d508efbcbbbbc0d。保留用于需求与设计参考；技术选型、接口、完成状态及开发约定不代表当前项目，以根目录 README.md、CONTEXT.md 和当前源码为准。

---
status: accepted
---

# 使用可替换的Mock、Snapshot、Live和Hybrid Provider

业务层只依赖统一Provider契约和标准对象，不直接依赖第三方API。开发期使用Mock跑通完整功能，真实数据可以通过数据库快照或实时API逐步替换；Hybrid模式优先实时数据并以缓存或快照降级，所有模拟、过期和降级数据必须进入DataSnapshot并对用户可见。

