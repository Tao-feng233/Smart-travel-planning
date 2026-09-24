---
status: accepted
---

# 使用可替换的Mock、Snapshot、Live和Hybrid Provider

业务层只依赖统一Provider契约和标准对象，不直接依赖第三方API。开发期使用Mock跑通完整功能，真实数据可以通过数据库快照或实时API逐步替换；Hybrid模式优先实时数据并以缓存或快照降级，所有模拟、过期和降级数据必须进入DataSnapshot并对用户可见。

