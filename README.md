# 候诊闻语 · 中医科诊前 AI 语音预问诊系统

患者候诊时微信扫码 → 大按键键盘录入就诊号 → AI 语音多轮问答采集病情 → 医生面诊前查看九栏目结构化摘要。
**仅为面诊辅助参考工具：不是电子病历、不做诊断、不开药。**

## 快速开始（开发）

```bash
# 后端（mock 模式无需任何 Key）
cd server
pip install -r requirements.txt
python run.py            # http://127.0.0.1:8000（无前端产物时显示占位页）

# 前端
cd web
npm install
npm run dev              # 开发调试；npm run build 产出 dist/
```

## 生产部署

见 `docs/delivery/部署运维手册.md`，一条脚本：`bash deploy/deploy.sh`。

## 文档地图

| 文档 | 内容 |
|------|------|
| docs/pm/候诊闻语-产品需求说明书.md | PRD v1.1（业务规则/验收标准/适老化一票否决项）|
| docs/research/R1-R4 | 调研报告（工程实践/选型/MiMo API/微信H5适老化）|
| docs/design/架构设计文档.md | 分层架构/API 规范/内存会话白名单设计 |
| docs/process/ | 环境盘点/决策日志/双视角评审/多智能体留痕 |
| docs/delivery/ | 部署手册/故障排查/配置说明/依赖清单/测试报告 |
| deploy/ | deploy.sh / nginx / systemd / backup / .env.example |

## 核心约束（改代码前必读）

1. **适老化一票否决**：患者端任何改动须满足 PRD 1.6 A1-A9（特大字/大按钮/无系统键盘/无精细手势）
2. **隐私白名单**：磁盘只存四字段（就诊号/提交时间/轮次/摘要）；音频即弃、轮次文本仅存内存
3. **合规红线**：任何路径不得输出诊断/治疗/用药建议（safety.py 服务端兜底）
4. 失败不计轮次；30s 超时；iOS 微信引导 Safari 是产品行为不是 bug

## 测试

```bash
cd server && python -m pytest tests -q   # 39 项，当前全绿
```
