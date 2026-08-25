# R3 - MiMo 开放平台 API 及备选供应商调研

> 调研日期：2026-08-24
> 调研人：AI 能力供应商接口调研员（R3）
> 项目背景：中医科诊前预问诊 H5。核心链路为"患者语音(base64 音频) → 大模型直接理解 → 输出下一轮提问文本或结束标记 + 结构化病情摘要 → 文本转语音播报给老人"。会话上下文由我方服务端维护，要求第三方不留存会话。
> 诚实性声明：本报告逐项标注【已证实】(附来源 URL) 与【未证实-基于行业惯例的合理假设】。凡未在官方文档中核实到确切 schema 的细节，一律按假设处理，并给出适配层隔离方案。

---

## 一、结论摘要

### 1.1 当前可实现性判断：**可实现，推荐采用"MiMo OpenAI 兼容接口直连 + 适配层隔离"方案**

产品需求指定的 `mimo-v2.5` 与 `mimo-v2.5-tts` 均真实存在且当前在线，关键能力与项目链路逐一对应：

| 项目链路环节 | MiMo 对应能力 | 状态 |
|---|---|---|
| 患者语音 base64 直接理解 | mimo-v2.5 全模态模型，`input_audio` content part 支持 Data URL(base64)，无需先转文本 | 【已证实】 |
| 多轮对话上下文 | 标准 OpenAI messages 数组，由我方服务端拼装传入 | 【已证实】 |
| 结构化病情摘要 | response_format 支持 `json_object` JSON 模式 | 【已证实】 |
| 提问文本转语音播报 | mimo-v2.5-tts，返回 base64 wav / 流式 pcm16 | 【已证实】 |
| 服务方不留存会话 | 隐私政策承诺"目的完成后删除或匿名化""未经同意不用于训练"，但**无零留存承诺** | 【部分证实，存在合规缺口】 |

成本侧重大利好：**mimo-v2.5-tts 系列（含 voiceclone/voicedesign）限时免费**【已证实】，mimo-v2.5 输入 ¥1/百万 tokens、输出 ¥2/百万 tokens，预问诊场景单次会话成本预计在分钱级别。

主要风险不在 API 可用性，而在三点：(1) 平台仅支持小米账号个人实名登录，企业主体采购需确认；(2) 隐私政策无"不留存"硬承诺，医疗场景建议走企业协议补充约定；(3) 单账号 RPM 100 限流，需做并发控制。

### 1.2 关键事实速览

- 官网/文档站：`https://mimo.mi.com`（中文文档路径前缀 `/docs/zh-CN/...`）
- 控制台：`https://platform.xiaomimimo.com/#/console/api-keys`
- OpenAI 兼容 Base URL：`https://api.xiaomimimo.com/v1`
- Anthropic 兼容 Base URL：`https://api.xiaomimimo.com/anthropic`
- Token Plan 订阅 Base URL：`https://token-plan-cn.xiaomimimo.com/v1`

---

## 二、MiMo 平台查证结果

### 2.1 平台入口与账号体系

| 项目 | 结论 | 状态 |
|---|---|---|
| 官方域名 | `mimo.mi.com`（文档/价格/新闻），`platform.xiaomimimo.com`（控制台），音频示例文件托管于 `example-files.cnbj1.mi-fds.com`，静态资源 CDN `aistudio-cdn.xiaomimimo.com` | 【已证实】来源：[mimo.mi.com](https://mimo.mi.com)、[首次调用 API](https://mimo.mi.com/docs/zh-CN/quick-start/summary/first-api-call) 页面正文及页面内嵌链接 |
| 控制台地址 | `https://platform.xiaomimimo.com/#/console/api-keys`（创建 Key）、`/console/balance`（充值）、`/console/usage`（用量）、`/console/plan-manage`（套餐管理） | 【已证实】同上，页面导航链接原文 |
| 登录方式 | **仅支持小米账号登录，且"目前平台仅提供个人账号登录方式"**；可在控制台注册或经 `id.mi.com` 注册 | 【已证实】《首次调用 API》页原文："目前平台仅提供个人账号登录方式" |
| API Key 申请 | 控制台创建。按量付费 Key 格式 `sk-xxxxx`；Token Plan 订阅 Key 格式 `tp-xxxxx`，两者额度不互通 | 【已证实】《首次调用 API》页 |
| 计费模式 | 预充值模式（控制台充值，按 token 消耗扣费）；另有 Token Plan 包月/包年订阅 | 【已证实】模型页与定价页 |
| 备案信息 | "Xiaomi MiMo: 备案号 Beijing-XiaomiMiMo-202601050182；小米大语言模型算法：网信算备110108916280901240011号；京ICP备17028681号-55" | 【已证实】各页页脚 |

> ⚠️ 注意事项：官方公告"MiMo-V2 系列模型已于 2026.6.30 00:00 正式下线，原模型名称已失效"。产品需求中的 `mimo-v2.5` 属现行 V2.5 系列，命名正确。此事件同时提示**该平台存在强制模型更迭历史**，适配层必须把 model 名做成配置项。

### 2.2 mimo-v2.5 多模态对话接口

#### Endpoint 与鉴权

- **Endpoint**：`POST https://api.xiaomimimo.com/v1/chat/completions`【已证实】来源：[OpenAI Chat Completion API 参考](https://mimo.mi.com/docs/zh-CN/api/chat/openai-api)、[音频理解指南](https://mimo.mi.com/docs/zh-CN/quick-start/usage-guide/multimodal-understanding/audio-understanding)
- **鉴权**：curl 示例使用请求头 `api-key: $MIMO_API_KEY`；官方 Python 示例通过 OpenAI SDK 传 `api_key=` 参数（即发送标准 `Authorization: Bearer <key>` 头）。两种头均可用的判断中，`api-key` 头有 curl 原文背书；`Authorization Bearer` 由 SDK 示例间接印证——**实现时优先用 Authorization Bearer（OpenAI SDK 默认行为），失败再降级 api-key 头**。【鉴权双头并存：已证实存在两种写法；兼容性细节：未证实-需实测】

#### 请求体结构（OpenAI Chat Completions 兼容）

以下参数均在 [OpenAI Chat Completion API 参考](https://mimo.mi.com/docs/zh-CN/api/chat/openai-api) 的请求体 schema 中出现：【已证实】

```jsonc
POST https://api.xiaomimimo.com/v1/chat/completions
Headers:
  Content-Type: application/json
  Authorization: Bearer sk-xxxxx        // 或 api-key: sk-xxxxx

{
  "model": "mimo-v2.5",
  "messages": [
    { "role": "system", "content": "..." },
    { "role": "user",   "content": [
        { "type": "input_audio", "input_audio": {
            // data 字段接受两种取值：
            // 1) 公网音频 URL，文件 ≤100MB
            // 2) Data URL 形式 base64："data:{MIME_TYPE};base64,$BASE64_AUDIO"
        }},
        { "type": "text", "text": "请听录音并回答" }
    ]}
  ],
  "max_completion_tokens": 1024,   // mimo-v2.5 默认 32768，范围 [1,131072]
  "temperature": 1.0,
  "top_p": 0.95,
  "stream": false,
  "stop": null,
  "frequency_penalty": 0,
  "presence_penalty": 0,
  "response_format": { "type": "text" | "json_object" },  // 仅列出 text/json_object 两档
  "thinking": { "type": "disabled" }   // 深度思考开关，官方示例即此写法
}
```

- **消息格式**：system/user/assistant/developer 角色，user content 为字符串或 content parts 数组（text / image_url / input_audio / video_url 四种 part 类型）。API 参考 schema 明确注明："**当前仅 mimo-v2.5 模型支持图像、音频或视频输入**"。【已证实】
- **响应体**：标准 OpenAI chat.completion 结构，`choices[].message.content` 为文本输出；usage 中含 `prompt_tokens_details.audio_tokens`（音频输入 token 数）。【已证实】官方示例响应见音频理解指南。
- **音频 Token 换算**：总 Tokens ≈ 音频时长（秒）× 6.25（即约每 8 秒音频 50 tokens）。【已证实】音频理解指南原文。
- **深度思考**：mimo-v2.5 返回字段额外含 `reasoning_content`（思考内容与正文分离）。多轮工具调用时官方建议回传历史 reasoning_content。【已证实】《首次调用 API》页。本项目问答场景建议关闭思考模式（`thinking: {"type":"disabled"}`）以降低时延。

#### 音频输入限制

| 限制项 | 数值 | 状态 |
|---|---|---|
| 支持格式 | MP3, WAV, FLAC, M4A, OGG（官方注明"格式变种较多，不能保证所有文件都能被识别"） | 【已证实】 |
| URL 方式大小上限 | 单文件 ≤ 100MB | 【已证实】 |
| Base64 方式上限 | Base64 字符串 ≤ 50MB（原始音频约 ≤37MB；16kHz/16bit/单声道 WAV 约 26 分钟） | 上限数值【已证实】；37MB/26分钟换算为本报告推算 |
| MIME 前缀 | 必须携带 `data:{MIME_TYPE};base64,` 前缀 | 【已证实】 |
| 音频数量 | 多条音频总量受上下文窗口限制 | 【已证实】 |

#### 上下文传递方式

标准 OpenAI 式无状态调用：**每次请求由客户端传完整 messages 数组，服务端不代管会话**。官方未见任何 conversation/session id 概念（Prompt Cache 缓存命中仅是计费折扣，不是会话存储）。这与我方"上下文由我方服务端维护"的架构天然一致。【已证实-基于全部已抓取文档均无 session 字段】

#### 模型规格、计费与限流

| 项 | mimo-v2.5 | 状态 |
|---|---|---|
| 模态 | 输入：文本/图像/视频/音频；输出：文本 | 【已证实】 |
| 定位 | 原生全模态感知模型，全模态理解/深度思考/工具调用/流式/联网搜索/结构化输出 | 【已证实】 |
| 上下文窗口 | 1M tokens；最大输出 128K | 【已证实】 |
| 限流(RPM/TPM) | 100 / 10M（按账号下所有 Key 汇总，同一模型共享） | 【已证实】[速率限制](https://mimo.mi.com/docs/zh-CN/api/guidance/rate-limit) |
| 价格(国内) | 输入缓存命中 ¥0.02/百万tokens；未命中 ¥1.00；输出 ¥2.00；缓存写入限时免费 | 【已证实】[按量计费定价页](https://mimo.mi.com/docs/price/pay-as-you-go)，更新时间 2026-08-06 |
| 海外价格 | $0.0028 / $0.14 / $0.28 每百万tokens | 【已证实】 |
| 成本估算 | 患者每轮回答约 15 秒语音 ≈ 94 audio tokens ≈ 0.000094 元；整轮对话(系统提示+多轮+输出)估算 < ¥0.01 | 【未证实-基于已证实单价的合理推算】 |

#### 附带发现：专用 ASR 模型 mimo-v2.5-asr（备选链路）

平台另有独立 ASR 模型，走同一个 `/v1/chat/completions` 接口：

- 模型名 `mimo-v2.5-asr`，`extra_body.asr_options.language` 取值 auto/zh/en；仅支持 wav/mp3，base64 ≤10MB；流式与非流式均可。【已证实】[语音识别文档](https://mimo.mi.com/docs/zh-CN/quick-start/usage-guide/audio/Speech-Recognition)
- 计费按音频时长 ¥0.5/小时。【已证实】
- 用途定位：若实测发现 mimo-v2.5 直接"听"老年方言语音的准确率不足，可切换为"ASR→LLM"两段式链路作为降级预案（代价是多一次调用与信息损失）。

### 2.3 mimo-v2.5-tts 语音合成接口

全部来自[语音合成（MiMo-V2.5-TTS 系列）文档](https://mimo.mi.com/docs/zh-CN/quick-start/usage-guide/audio/speech-synthesis-v2.5)。【本节均已证实】

- **Endpoint**：与对话接口共用 `POST https://api.xiaomimimo.com/v1/chat/completions`，即官方示例为 `base_url = "https://api.xiaomimimo.com/v1"` 下 `chat.completions.create(model="mimo-v2.5-tts", ...)`；官方未提供独立 TTS endpoint。
- **特殊请求规则**：
  - 待合成文本必须放在 **role=assistant** 的消息里（不是 user！这是 MiMo TTS 与常见 TTS API 的最大差异点）；
  - role=user 消息可选，用于自然语言风格指令（如"用轻快上扬的语调……"），voicedesign 模型下必填；
  - 顶层参数 `audio`：`{"format": "wav" | "pcm16", "voice": "<voice_id>"}`；
  - 流式调用必须指定 `format: "pcm16"`（24kHz PCM16LE 单声道），分片在 `delta.audio.data`(base64) 中，需自行拼接；非流式返回 `message.audio.data` 为 base64 wav。
- **音色**（预置音色表）：`mimo_default`（中国集群默认"冰糖"）、冰糖/茉莉/苏打/白桦（中文女/女/男/男）、Mia/Chloe/Milo/Dean（英文）。面向老人的播报建议实测"茉莉"（中文女声）或"苏打"（中文男声）。
- **风格控制**：两种方式——① 自然语言指令放 user message；② 标签控制写在 assistant 文本内，如 `(温柔)` `(东北话)` `[吸气]` `(唱歌)`，支持复合情绪、语速节奏、方言、角色扮演等标签；另支持导演模式长描述。
- **模型变体**：`mimo-v2.5-tts-voicedesign`（文字描述定制音色，参数 `optimize_text_preview`）、`mimo-v2.5-tts-voiceclone`（音频样本克隆音色，隐私政策对声纹信息有专门授权条款）。
- **限制**：TTS 上下文 8K / 最大输出 8K tokens；RPM 100 / TPM 10M；voicedesign 低延迟流式暂未上线（流式接口降级为推理完再一次性返回）。
- **计费**：**mimo-v2.5-tts / voicedesign / voiceclone 三款均"限时免费"**（国内外同），更新时间 2026-08-06。"限时"截止时间官方未公布——【未证实】，须按随时恢复收费做预算兜底（参考竞品 qwen3-tts-flash 约 ¥0.8/万字符、豆包 TTS 套餐制）。
- **响应格式结论（针对项目问题"返回 wav/mp3/base64？"）**：返回 **base64 编码的 wav 或 pcm16 裸流**，不支持 mp3 输出；H5 端可直接 `Blob([bytes], {type:'audio/wav'})` 播放，或服务端转发二进制。

### 2.4 OpenAI 兼容性

- **结论：完全兼容 OpenAI Chat Completions 协议，base_url 替换即用**【已证实】。《首次调用 API》原文："Xiaomi MiMo API 开放平台兼容 OpenAI API、Anthropic API 两种主流 API 格式，您可以使用现有 SDK 来使用模型推理服务"；模型页原文："现有项目仅需修改 base_url 和 model 即可无缝迁移"。官方全部示例即用 openai Python SDK + `base_url="https://api.xiaomimimo.com/v1"`。
- 同时兼容 Anthropic Messages 协议（`/anthropic` 前缀）。【已证实】
- 另提供 OpenAI Responses API 兼容端点。【已证实-API 参考目录】
- 差异点提醒（写代码时注意）：① TTS 的"合成文本放 assistant 角色"为 MiMo 特有语义，与 OpenAI Audio Speech API 不同；② `input_audio.data` 同时接受 URL 和 Data URL，比 OpenAI 标准更宽；③ 存在私有扩展参数 `thinking`、`asr_options`（经 extra_body 传递）。

### 2.5 服务条款与数据留存（重点核查项）

- **隐私政策全文可访问**：`https://privacy.mi.com/XiaomiMiMoPlatform/zh_CN/`【已证实，本次调研已抓取全文核读】
- 关键条款摘录：
  - 收集范围："为了提供 Xiaomi MiMo API 及 Xiaomi MiMo Code 服务，我们需要收集您提供的**文本、图片、视频、音频信息**……还需要收集您的 IP 信息"【已证实】
  - 训练用途："**未经您的事先同意，小米不会将您提供的文本内容用于模型训练或者其他用途**"【已证实】
  - 保留政策："个人信息在完成收集目的，或在确认您的删除或注销申请后，或终止运营相应产品或服务后，我们将停止保留，并做删除或匿名化处理"【已证实】
  - 存储位置："您的信息将会保存至中华人民共和国境内"【已证实】
  - 声纹专项：音色模仿功能收集音频中的**声纹信息**，要求使用者确保获得信息主体同意（涉及敏感个人信息需单独同意）【已证实】——若未来启用 voiceclone 需患者书面授权，本项目默认不用。
- **合规结论（诚实判定）**：条款满足"不用于训练、目的达成后删除/匿名化、境内存储"，但**没有找到"API 调用内容零留存/不留存会话"的明确承诺，也未公布具体留存期限数字**。【未证实-无法证实零留存】因此"第三方不留存会话"这一产品约束**不能仅凭公开条款视为完全满足**。缓解措施：① 医疗机构以企业主体与其签约时附加数据处理协议(DPA)；② 我方发送给 MiMo 的上下文尽量脱敏（不含姓名/身份证号等直接标识符）；③ 该风险列入第五章预案。
- 服务协议(user-agreement)正文为前端弹窗渲染，静态抓取不可得，本次未逐字核读【未证实-未能获取全文】；隐私政策已核读，为主要依据。

---

## 三、适配层设计建议

鉴于 MiMo 已证实为 OpenAI 兼容，且备选厂商也大多 OpenAI 兼容或接近，强烈建议服务端引入一层薄 Provider 抽象，将"供应商细节"压进配置。

### 3.1 Provider 抽象

```python
# server/app/providers/base.py （示意）
class VoiceAgentProvider(Protocol):
    async def understand(
        self, audio_b64: str, mime: str, history: list[dict],
        system_prompt: str,
    ) -> UnderstandResult:
        """音频 -> (next_question | END_MARK, summary_delta)。UnderstandResult 含结构化摘要。"""

    async def synthesize(self, text: str, style_hint: str | None = None) -> bytes:
        """文本 -> 音频字节流(wav)"""

class MiMoProvider:          # api.xiaomimimo.com/v1，chat/completions 直连
class BailianProvider: ...   # dashscope qwen-omni + qwen3-tts-flash
class VolcanoProvider: ...   # 豆包 ASR/LLM/TTS 组合
class MockProvider: ...      # 无 Key 本地开发与自动化测试
```

要点：
1. `understand()` 统一返回我方领域对象（下一轮提问 or 结束标记 + 摘要），屏蔽各家差异；结束标记用固定哨兵串（如 `"[[END]]"`）由 system prompt 约定，解析在我方侧完成。
2. 各 Provider 内部自行处理私有参数（MiMo 的 `extra_body.thinking`、百炼的 modalities 等），不出抽象边界。
3. 音频编码归一化：适配层统一接收 `audio_b64 + mime`，由各 provider 决定是否加 `data:` 前缀（MiMo 要求前缀，其他家多为裸 base64）。

### 3.2 配置化切换

```yaml
# .env / config.yaml 示意
provider: mimo            # mimo | bailian | volcano | mock
providers:
  mimo:
    base_url: https://api.xiaomimimo.com/v1
    api_key: ${MIMO_API_KEY}          # 环境变量注入
    model_chat: mimo-v2.5             # 平台有过 V2->V2.5 强制更迭史，必须可配
    model_tts: mimo-v2.5-tts
    tts_voice: 茉莉                    # 或 苏打/mimo_default
    tts_format: wav                   # 流式场景改 pcm16
    thinking_disabled: true           # 问答场景关闭深度思考降低时延
```

### 3.3 mock provider（无 Key 开发/测试）

- MockProvider 按"固定剧本 + 随机扰动"返回下一轮提问与摘要（覆盖正常轮、追问轮、结束轮三类），`synthesize()` 返回预生成的静音/短 wav 字节，保证 H5 全链路可跑通、CI 无外部依赖。
- 另建 `FakeOpenAIServer`（可用 aioresponses/respx 或本地 http server）验证 MiMoProvider 的请求体拼装是否符合 §2.2 schema，防止真实联调时才发现格式错误。
- 真实 Key 联调清单：① Authorization 与 api-key 双头实测；② 60s 以上老人语速 wav 实测识别质量；③ `response_format=json_object` 与音频输入同用时是否生效（官方文档未组合演示，属【未证实】项，需实测）；④ TTS 中文音色试听。

---

## 四、备选供应商对比

### 4.1 对比总表

| 维度 | 小米 MiMo（首选） | 阿里云百炼 | 火山方舟(豆包) | SiliconFlow | 自建 OpenAI 兼容 |
|---|---|---|---|---|---|
| 语音直入 LLM | ✅ mimo-v2.5 原生 input_audio | ✅ qwen-omni-turbo / qwen3-omni-flash | ⚠️ 主推 ASR→LLM 两段式（Doubao_Seed_ASR_2.0 + 豆包 LLM） | ❌ ASR 与 LLM 分离 | 视部署模型而定 |
| TTS | mimo-v2.5-tts，wav/pcm16 | qwen3-tts-flash 等 | 豆包 TTS（V3 接口，WebSocket/HTTP） | CosyVoice2-0.5B | CosyVoice/GLM-TTS 自部署 |
| 鉴权 | Bearer / api-key | Bearer(DASHSCOPE_API_KEY) | 火山签名(AK/SK)+Bearer | Bearer | 自定 |
| OpenAI 兼容 | ✅ 官方声明 | ✅ compatible-mode 端点 | ⚠️ LLM 部分兼容，语音接口自有协议 | ✅（ASR 为 multipart 端点） | ✅ 天然 |
| 计费参考 | 输入¥1/M tok，输出¥2/M tok；ASR ¥0.5/h；**TTS 限时免费** | qwen-omni-turbo 音频输入 ¥25/M tok（qwen3-omni-flash 音频 ¥15.8/M）；qwen3-tts-flash ¥0.8/万字符 | Seed ASR 流式 4.5 元/h；TTS 按次套餐（如 ¥22.5 起） | SenseVoice ASR 免费；CosyVoice2 ¥0.05/千字符 | GPU 成本为主 |
| 免费额度 | 未证实有新户额度 | 100 万 token（90 天） | 有体验券（未核实数额） | ASR 免费 | — |
| 限流 | RPM 100/TPM 10M | RPM 60/TPM 10万(qwen-omni-turbo) | QPS 10-20（语音类） | 未证实 | 自控 |
| 企业签约 | ⚠️ 目前仅个人账号登录，企业采购待确认 | ✅ 成熟企业流程 | ✅ 成熟企业流程 | ✅ 支持 | — |
| 数据留存条款 | 目的完成后删除/匿名化，无零留存承诺 | 企业版可签数据不留存（需商务确认）【未证实-需商务确认】 | 同左 | 公开条款较简单【未证实】 | 数据完全自持 ✅ |
| 接入难度 | ★☆☆☆☆ 极低（OpenAI SDK 换 base_url） | ★★☆☆☆ 低（omni 走 compatible-mode，TTS 是另一套 multimodal-generation 端点，两套接口） | ★★★★☆ 高（语音走 WebSocket 自有协议+签名，LLM 另接） | ★★☆☆☆ 低（但链路拆成 ASR+LLM+TTS 三段） | ★★★☆☆ 中（免对接但要运维 GPU 推理） |

### 4.2 各备选小结

**阿里云百炼（qwen-omni + qwen-tts）** —— 最现实的 Plan A'。
- qwen-omni-turbo：音频输入 ¥25/百万 tokens（约 25 tok/秒，比 MiMo 的 6.25 tok/秒贵一个数量级），上下文 32K，RPM 60；新一代 qwen3-omni-flash 音频输入 ¥15.8/M 更便宜。【已证实-来自搜索汇总的官方帮助中心数据，建议实施前以 help.aliyun.com 实时价为准】
- qwen2-audio-instruct 已停止付费选项，官方引导迁移至 Omni 系列。【已证实】
- TTS：qwen3-tts-flash ¥0.8/万字符（汉字计 2 字符），HTTP/SSE 端点 `dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation`，音色 Cherry/Serena/Ethan/Chelsie/Momo 等，支持声音描述自定义音色；返回音频 URL(24h 有效)或 base64。【已证实-搜索汇总】
- 评估：能力齐、企业合规成熟、文档完善；缺点是 omni 音频单价高、TTS 与对话是两套 API（适配层要写两个方法映射），以及限流较低。

**火山方舟（豆包语音）** —— 效果强但接入最重。
- 语音链路以专业语音引擎为主：Doubao_Seed_ASR_Streaming_2.0（4.5 元/小时，QPS 10）、录音文件识别 2.0（0.8 元/小时）、TTS 大模型 V3 接口（wss://openspeech.bytedance.com/api/v3/tts/bidirection 等 WebSocket/HTTP Chunked/SSE）。【已证实-搜索汇总自火山引擎官方文档】
- "大模型直接听音频"并非其主推形态，需 ASR→LLM→TTS 三段拼接，会话状态管理复杂度最高；优点是方言识别与老年语音效果口碑好、企业流程完善。
- 适合作为"识别质量兜底"的二备选而非首选。

**SiliconFlow（硅基流动）** —— 最便宜的拼装方案。
- ASR：SenseVoiceSmall / TeleSpeechASR / Qwen3-ASR-1.7B 免费，`POST https://api.siliconflow.cn/v1/audio/transcriptions`（multipart，≤1 小时/50MB）；TTS：CosyVoice2-0.5B ¥0.05/千字符，支持零样本克隆。【已证实-搜索汇总自官方定价页与 API 文档】
- 无"音频直入 LLM"能力，链路为 SenseVoice(ASR)→任意 LLM→CosyVoice(TTS) 三段；三段均为 OpenAI 风格接口，适配成本低。
- 评估：开发调试期几乎零成本跑通链路的首选试验场；生产上 ASR 免费档位的服务等级与医疗场景稳定性需要评估【未证实】。

**OpenAI-compatible 自建方案** —— 数据主权最强。
- 思路：vLLM/Ollama 等推理框架部署开源全模态模型（Qwen2.5-Omni/Qwen2-Audio、GLM-4-Voice 等），或 FunASR(SenseVoice)+LLM+CosyVoice 三件套自建，对外暴露 OpenAI 兼容端点。
- 所有 schema 细节依赖所选框架版本【未证实-基于行业惯例的合理假设】，且医院内网 GPU 资源、运维人力是硬门槛。
- 定位：合规压力极大时的终极退路，不作为近期方案。

---

## 五、风险与预案

| # | 风险 | 等级 | 预案 |
|---|---|---|---|
| 1 | **数据留存合规缺口**：MiMo 隐私政策无"零留存"承诺，仅"目的完成后删除/匿名化"；医疗健康语音属敏感个人信息 | 高 | ① 会话上下文与提示词中不带患者身份标识（仅传病情相关语音/文本）；② 推动院方/企业主体与小米签数据处理协议，明确"不留存、不训练"；③ 若无法闭环，切换百炼企业版或自建（第四章）；④ 患者知情同意书中明示第三方 AI 处理 |
| 2 | **TTS"限时免费"结束**：免费期无公布截止日，收费后成本跳升 | 中 | 预算按 qwen3-tts-flash 价位(≈¥0.8/万字符)预留；适配层 TTS 也做成可切 provider；监控账单告警 |
| 3 | **模型更迭史**：V2 系列 2026-06-30 强制下线先例，V2.5 未来也可能更名/下线 | 中 | model 名全部配置化；适配层对 404/model_not_found 错误码做明确报错与配置热更新指引 |
| 4 | **限流**：单账号 RPM 100（所有 Key 共享），高峰期 429 | 中 | 客户端信号量限并发 + 429 指数退避重试；TPM 10M 对本业务极充裕，瓶颈只在 RPM；必要时多账号（注意 ToS 合规性需确认【未证实】） |
| 5 | **老年方言语音识别质量未实测**：官方宣称支持方言的是 ASR 模型，mimo-v2.5 直接听音频对方言/口齿不清老人的效果无公开基准 | 中高 | 开发期尽早真机实测（川渝/粤语老人样本）；不达标则切"mimo-v2.5-asr → mimo-v2.5-pro 文本对话"两段式，接口形态不变，仅适配层内部改管线 |
| 6 | **JSON 模式与音频输入组合未验证**：response_format=json_object 与 input_audio 并用官方无示例 | 中 | 联调第一周列为 P0 实测项；失败则降级 prompt 约束 + 宽松 JSON 解析(json_repair) |
| 7 | **仅个人账号登录**：企业主体付款、发票、SLA 渠道不明 | 中 | 联系 platform.xiaomimimo.com/contact 商务渠道确认企业接入方式后再进入生产；开发期用个人 Key 不受影响 |
| 8 | **鉴权头细节**：Authorization Bearer 与 api-key 头并存，个别网关行为未知 | 低 | SDK 默认 Bearer；封装处留 header 注入开关，实测后固化 |
| 9 | **服务协议全文未核读**：正文前端渲染无法静态抓取 | 低 | 生产上线前人工浏览器通读 user-agreement 全文，重点看责任限制与数据条款，与本报告结论比对修订 |

## 六、附：本次调研实际核验的官方页面清单

- https://mimo.mi.com/models/zh-CN/mimo-v2.5 （模型规格/价格/接入示例）
- https://mimo.mi.com/docs/zh-CN/quick-start/summary/first-api-call （账号/BaseURL/Key）
- https://mimo.mi.com/docs/zh-CN/quick-start/summary/model （模型列表/限流）
- https://mimo.mi.com/docs/zh-CN/quick-start/usage-guide/multimodal-understanding/audio-understanding （音频理解：base64 传入方式）
- https://mimo.mi.com/docs/zh-CN/quick-start/usage-guide/audio/speech-synthesis-v2.5 （TTS：请求/响应/音色/流式）
- https://mimo.mi.com/docs/zh-CN/quick-start/usage-guide/audio/Speech-Recognition （ASR）
- https://mimo.mi.com/docs/zh-CN/quick-start/usage-guide/text-generation/structured-output （JSON 模式）
- https://mimo.mi.com/docs/zh-CN/api/chat/openai-api （Chat Completion 请求体 schema）
- https://mimo.mi.com/docs/zh-CN/api/guidance/rate-limit （限流表）
- https://mimo.mi.com/docs/zh-CN/price/pay-as-you-go （定价，2026-08-06 更新）
- https://privacy.mi.com/XiaomiMiMoPlatform/zh_CN/ （隐私政策全文）
