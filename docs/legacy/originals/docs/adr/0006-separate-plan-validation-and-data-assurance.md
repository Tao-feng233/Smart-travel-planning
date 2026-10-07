> 历史设计资料：原仓库提交 dc53d5b3c914bf4c446809b01d508efbcbbbbc0d。保留用于需求与设计参考；技术选型、接口、完成状态及开发约定不代表当前项目，以根目录 README.md、CONTEXT.md 和当前源码为准。

---
status: accepted
---

# 分离计划可行性、数据可信度和攻略生命周期

行程逻辑正确不代表数据真实可靠，因此TravelGuide分别维护PlanValidationStatus、DataAssuranceStatus和GuideLifecycleStatus，并由它们共同决定GuideReadiness。Mock数据可以生成逻辑有效的演示攻略，但必须显示模拟标识，关键事实不足时不能发布为READY。

