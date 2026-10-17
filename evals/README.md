# 评测与证据等级

## 已有行为用例

`evals.json` 保留原有 8 个场景以及全局版的 PPT 导演规划场景。`phase1.json` 新增 6 个记录/续作场景。它们是待执行的行为评测定义，不是已通过报告。

## 离线回归

在 Skill 根目录执行，Python 3.12+，不调用模型、不花生图费用：

```text
python -m unittest discover -s tests -v
python evals/prepare_fixture.py PRIVATE_FIXTURE_DIR
python scripts/records.py PRIVATE_FIXTURE_DIR
python scripts/sync_skill.py .
```

测试使用临时目录、公开样例图片和明确标为虚构的确认证据；测试结束自动清理临时目录。prepare_fixture 则保留供行为重放用的夹具，目标目录必须不存在。它不会生成新图，只复制现有公开样例。

夹具的客观预期：01 已有图、待审核；02 结果未知；03 失败；04 未开始。应只把 03/04 列入待生成，02 先核实，不能将 01 当作用户认可。

单元测试验证真实文件存在/哈希、参考参数对应、角色版本与确认字段、返修父版本、新输出路径、PPT 前置批准和安装副本完整性。不能证明模型遵守了 prompt、用户长相相似或新对话已经加载技能。

## 新旧版本行为对照

1. 保留改动前 Skill 快照，不覆盖；新旧版分别使用同一份原始夹具的独立副本。
2. 在相同模型/工具环境中，按 phase1.json 的 prompt 重放。`files` 相对于夹具根目录，必须把整个夹具目录给执行者，以便其读取记录引用的 prompt/receipt。
3. 记录实际版本/commit、模型、用例、实际工具调用、执行耗时、可获取时的 token、产出路径。计时或 token 不可得写 null，不能估填。
4. 对每条 expectations 保存 passed/failed/not_run 以及对应文件或调用证据。不用标题/关键词命中替代行为验证。
5. 人工并排看结果，评判 human_review；发现问题再窄范围修正。对照执行未发生时必须标 not_run，不能用单元测试替代模型行为评测。

## 真实图片验证

人物相似度需要用户授权照片和已确认锚图，保存在私有评测目录，绝不进入公共 eval 附件。待用户授权出图后，再比较改衣服、换动作、小比例角色和指定文字返修的结果。

报告分开列：离线测试、模型行为重放、真实图片审核、用户认可。自动 QA 通过不能晋升后三项；不以通用人脸识别分数冒充用户的 IP 相似度判断。

## 借鉴来源

- [baoyu-comic](https://github.com/JimLiu/baoyu-skills/blob/main/skills/baoyu-comic/SKILL.md)：逐图 prompt、角色参考与局部返修。
- [Anthropic skill-creator](https://github.com/anthropics/skills/blob/main/skills/skill-creator/SKILL.md)：旧版对照、断言证据和人工评审。
- [Vercel skills](https://github.com/vercel-labs/skills)：明确安装范围与维护来源。

本次脚本为本项目实现，没有复制上述项目源代码；没有安装它们作为运行依赖。
