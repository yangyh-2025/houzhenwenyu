# 候诊闻语 · 中医科诊前 AI 语音预问诊系统

> 患者候诊时微信扫码，用"说话"的方式完成诊前病情采集；医生面诊前查看 AI 整理的结构化摘要。
> **仅为面诊辅助参考工具：不是电子病历、不做诊断、不开药，所有信息以医生线下望闻问切为准。**

![Python](https://img.shields.io/badge/Python-3.9%2B-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009485?logo=fastapi&logoColor=white)
![Vue](https://img.shields.io/badge/Vue-3-4FC08D?logo=vue.js&logoColor=white)
![Vite](https://img.shields.io/badge/Vite-8-646CFF?logo=vite&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-WAL-003B57?logo=sqlite&logoColor=white)
![License](https://img.shields.io/badge/License-PolyForm%20NC%201.0-blue)

## ✨ 核心特性

**患者端（适老化 H5，微信扫码即用）**
- 🎙️ **按住说话**：微信语音同款交互，按住录音、松开即传，零打字
- 🔢 **大按键数字键盘**：唯一必录信息是就诊号，绝不调起系统键盘
- 📊 **问诊进度条**：第 X/8 步 + 剩余问题预期，老人心里有数
- 🔁 **当日续问**：中途退出重扫码，从上一问继续；一号一条，提交即更新
- 🗣️ **全程语音+文字双通道**：AI 每句提问同步显示大字文本
- ⏳ **等待预期管理**：暖性话术轮播（理解病情/查阅知识库…），不再"AI思考中"

**医生端（移动后台）**
- 📋 八栏目结构化摘要（主诉/病程/症状/饮食/睡眠/二便/病史/用药）
- 🌿 **中医辨证参考**（AI 生成·仅供医生参考，患者端不可见）
- 🔐 账密登录 · 5 次锁定 · 30 分钟超时登出
- 🔍 就诊号快速查询

**工程与合规**
- 🛡️ 三层医疗建议防线（提示词约束→输出过滤→历史消毒），15 条攻击语料测试全拦
- 🔒 隐私白名单：磁盘仅存四字段；原始录音即弃、轮次文本不落盘
- 💰 额度防护：AI 调用硬预算 + RPM 节流 + 限流三池（20 人并发实测达标）
- 🧹 挂号日制：每日 02:00 自动重置数据，一号对应当日一人

## 🏗️ 架构

```
患者微信/Safari ──HTTPS──> Nginx(TLS+静态) ──> FastAPI ──> MiMo 开放平台
                                             │            (mimo-v2.5 理解
                                        SQLite(WAL)       + mimo-v2.5-tts 冰糖声)
```

- **语音链路**：浏览器 ScriptProcessor 采集 PCM → 前端重采样 16kHz 单声道 WAV → ASR 转写 → 大模型多轮引导 → TTS 合成 mp3 二进制直传（省 87% 带宽）
- **供应商抽象**：`AI_PROVIDER=mimo|mock`，无 Key 全功能演示模式

## 🚀 快速开始

```bash
# 后端（mock 模式无需 API Key）
cd server && pip install -r requirements.txt
python run.py                    # http://127.0.0.1:8000

# 前端
cd web && npm install && npm run build
```

生产部署（空白 Linux 一条脚本）：见 `docs/delivery/部署运维手册.md`

## 📂 文档

| 目录 | 内容 |
|------|------|
| docs/pm | 产品需求说明书（v1.8，业务规则/验收标准/适老化一票否决项）|
| docs/research | 调研报告（MiMo API schema 实证 / 微信H5录音红线 / 适老化标准）|
| docs/design | 架构设计文档 |
| docs/delivery | 部署运维手册 / 故障排查 / 安全加固报告 / 压测报告 |

## 🧪 测试

```bash
cd server && python -m pytest tests -q   # 62 项单元+集成测试
```

## ⚠️ 医疗免责声明

本系统输出的全部内容（包括摘要与辨证参考）均由 AI 生成，**不构成医疗诊断、治疗建议或处方**；
临床决策责任完全在于执业医师。患者端不展示任何诊断性内容。

## 📄 License（非商业许可 · PolyForm Noncommercial 1.0.0）

本项目采用国际通行的 **[PolyForm Noncommercial 1.0.0](https://polyformproject.org/licenses/noncommercial/1.0.0)** 许可：

- ✅ **个人学习、研究、教学、非商业用途**：免费使用、修改、分发
- ⛔ **任何商业用途**（销售/收费服务/企业经营性部署/嵌入商业产品）：须另行获得版权人书面授权
- ⛔ **修改版商用**：同样须获书面授权，再分发须沿用本许可

商业授权请联系：**yangyuhang2667@163.com** ｜ 完整条款见 [LICENSE](LICENSE)
