# 角色资产与生成记录

适用于角色建档、三种内容模式、返修和新对话续作。记录是私有项目数据，不写入公共 Skill 包。

## 私有目录

每个系列使用一个稳定目录，例如工作区 `outputs/creator/series/`。用户指定路径优先。

```text
series/
  character.json
  batch.json
  character-assets/v1/main.png
  prompts/01-v1.md
  generations/01-v1.json
  receipts/01-v1.json
  images/01-v1.png
  qa/01-v1.md
```

从 `templates/` 复制模板，填写真实已知值。空数组/null 表示未填写，不是通过校验的示例。所有记录内文件路径相对该目录，使用 `/`，禁止越界或指向外部的链接。原始照片留在用户指定位置；只有生成确实需要且用户授权使用的材料才复制进私有目录。不自动扫描其他用户文件。

辅助命令需要 Python 3.12+，仅用标准库。下文在 Skill 根目录执行，ROOT 替换为私有系列目录：

```text
python scripts/records.py ROOT
python scripts/records.py ROOT --preflight 01-v1
```

计算文件 SHA-256 可以用 PowerShell `Get-FileHash -Algorithm SHA256`（保存为小写），或 Python `hashlib.file_digest`。哈希用于发现文件变更，不证明画面质量。

## character.json

- `character_id`：稳定角色标识；`active_version`：已获用户确认的默认版本，没有则为 null。
- `versions[]`：每个版本独立保留 `version`、`parent_version`、`change_request`。
- `status`：candidate / approved / rejected。新生成版本始终先为 candidate；不能因为它更新就替换 active_version。
- `anchors.face/outfit/style`：分别记录脸型五官、服装、画风约束，避免改衣服时重设计脸。
- `assets[]`：`role` 为 main / action / spec；每项含 `path` 和 `sha256`。确认后的版本至少有 main；三件套其他资产按原流程补齐，尚缺时不得声称已完成。
- `approval`：用户真实确认的记录，格式见下。仅在确认具体版本后设置 approved 并更新 active_version。

```json
{"source":"user","evidence":"对话消息定位及用户原话，明确确认的版本","at":"2026-10-16T12:00:00Z"}
```

不要把“继续”、无反馈、自动 QA 通过推断为身份认可。用户先前已明确认可的同一版本可以沿用原证据，不逐页重复询问。历史材料缺失时保持 unknown/null 并说明，不能补造确认时间。

“第一版脸型，但不要外套”：定位第一版文件，新建带 parent_version 的候选；face/style 保留，outfit 记录改变；生成时传第一版图，并说明只替换服装。新候选经用户确认才更新默认版本。旧版本不覆盖。

## generations/*.json

每个生成尝试一份记录，文件名与 run_id 对应；先保存 prompt 与 planned 记录，再执行 preflight。

- `item_id` 稳定标识页/卡；`run_id` 标识本次尝试；`parent_run` 指向同一页的上次尝试。改第三张不改其他页 ID。
- `purpose` 为 character 或 content；`mode` 为 character / illustration / knowledge-card / ppt。角色创建允许 candidate；内容必须引用 approved 角色版本。
- `uses_character` 表示本图是否出现用户 IP。PPT 数据页等可以为 false，仍保留系列角色版本。
- `preserve` 和 `change` 分开记录不变项、修改项；`change_request` 保存本轮要求。
- `prompt`、`references[]`、`output`、`qa.evidence`、`invocation.receipt` 都是 `{path, sha256}`。references 另含角色 main/action/spec/source/style/edit，按实际传图顺序排列；内容里出现 IP 时必须包含对应已批准 main。
- `output_path` 是为本次尝试预留的新路径。一次只生成一张，返修使用新 run_id 和新输出文件，不能覆盖旧图或旧提示词。
- `backend` 记录实际工具及是否支持参考图。不支持时不要默认纯文字继续身份生成；先交付 prompt 或使用用户已明确同意的降级，并保存 `downgrade_approval`。

状态转换：planned -> running -> generated / failed / unknown。调用前设置 running；得到工具确认的失败才标 failed；超时/中断且不确定是否成功标 unknown。先核实工具结果与文件，再决定重试。不要仅凭文件名存在把未知结果标为完成。

工具返回后，记录 **实际调用**，而非计划中的参数。保留工具调用标识、输入/输出路径和实际参数快照，去掉令牌、凭据和不相关响应；保存到 receipt 文件。示例：

```json
{
  "tool": "image_gen",
  "reference_parameter": "referenced_image_paths",
  "arguments": {"referenced_image_paths": ["character-assets/v1/main.png"]},
  "receipt": {"path": "receipts/01-v1.json", "sha256": "实际文件哈希"}
}
```

`arguments` 保存实际传给工具的参数，绝对图片路径也允许；校验器将其解析后与 references 比对。当前校验器支持路径列表型参考参数；宿主若只有“最近图片数量”接口，先用宿主支持的方式将目标图落盘并切换路径参数。无法转换时明确记录能力限制，不伪造路径参数以通过校验。提示词中写“参考第一版”不等于传图。

工具输出先非破坏性复制到 output_path，再记录哈希和 generated。原始工具输出保留。SHA、尺寸与参数检查只能证明文件和记录一致，不能证明模型真的遵守了参考图。

`qa.status`：pending/pass/fail。非 pending 时必须有实际检查报告文件；报告分别写文件检查、视觉检查、文字检查、未验证项。没有看图就不能声称视觉通过。

`user_review`：null 或用户证据对象加 `decision: approved/rejected`。自动 QA 不更新此字段，也不自动更新角色 approval。

## batch.json 与续作

- `items` 保存获授权批次的固定页/卡 ID；`latest_runs` 给每项一个最新 run_id，没有尝试则 null。
- `sample_items` 在 PPT 模式为 1-2 个代表页；`approvals.plan/samples` 使用真实用户证据。原有导演规划和样张批准门保留。
- 新对话先读这三个记录来源和实际文件，不从聊天印象猜进度。确认过的批次按原授权继续。
- 校验结果的 `to_generate`：未开始、planned 或明确失败的项。failed 重试新建尝试，不改写失败历史。
- `in_flight/reconcile`：执行中或结果未知，不能盲目重试。
- `review`：有图但未获用户认可；`repair`：QA 或用户拒绝；`approved`：有用户认可。三者都不属于自动补图列表。
- 用户指定返修时，仅为该 item 新建尝试；完成后更新其 latest_runs。generated 不等于 approved，更不等于已发布。
- `--preflight` 检查指定 planned 尝试；PPT 样张需规划批准，非样张需规划与样张批准。校验通过之后再调用工具。

结束时报告本次完成/失败/待审项、角色版本和完整输出路径。不要把 JSON 字段当成需要用户填写的问卷。
