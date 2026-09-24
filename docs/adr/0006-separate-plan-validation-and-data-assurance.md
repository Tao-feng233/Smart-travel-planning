---
status: accepted
---

# 分离计划可行性、数据可信度和攻略生命周期

行程逻辑正确不代表数据真实可靠，因此TravelGuide分别维护PlanValidationStatus、DataAssuranceStatus和GuideLifecycleStatus，并由它们共同决定GuideReadiness。Mock数据可以生成逻辑有效的演示攻略，但必须显示模拟标识，关键事实不足时不能发布为READY。

