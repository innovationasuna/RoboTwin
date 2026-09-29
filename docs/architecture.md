# Architecture / 系统架构

[English overview](../README.md) · [中文首页](../README.zh-CN.md) · [Experiments](experiments.md)

GAPA composes supported robot skills into programs, executes them in RoboTwin, and uses execution evidence to guide corrections. It combines three agent roles with deterministic checks and simulator-aware skills.

GAPA 将支持的机器人技能组合为程序，在 RoboTwin 中执行，并利用执行证据指导修正。三个 Agent 负责语义与程序推理，确定性检查和依赖仿真信息的技能负责执行约束。

## Agent roles / Agent 分工

| Role / 角色 | Input / 输入 | Output / 输出 |
| --- | --- | --- |
| Task Parser / 任务解析 | Instruction and available objects / 指令与可用物体 | A canonical TaskDSL checked against supported tasks / 经支持范围校验的 TaskDSL |
| Code Generation / 代码生成 | Task, skill API, relevant memory, previous feedback / 任务、技能接口、相关记忆与反馈 | A restricted `play_once(api)` program / 受限的技能程序 |
| Feedback Diagnosis / 反馈诊断 | Failure stage, API trace, success checks, current scene context / 失败位置、调用记录、判定结果与当前场景 | Structured diagnosis and guidance for the next attempt / 结构化诊断与下一次尝试的建议 |

The roles can use the same configured LLM. Feedback starts from deterministic evidence mapping and can add LLM guidance. The program validator is a rule-based gate, not a fourth reasoning model.

这些角色可以共用同一个已配置的 LLM。反馈诊断先对确定性证据进行归类，再由 LLM 补充建议；程序校验属于规则检查，不是第四个推理模型。

## Perception and execution / 感知与执行

- **Oracle:** obtains poses from simulator state. / 从仿真状态获取位姿。
- **VLM:** localizes supported objects and specialized drawer functional points in camera images; depth and camera transforms map image coordinates to world positions. / 在图像中定位支持的物体及专用抽屉功能点，再结合深度与相机变换获取世界坐标。
- **Skill library:** exposes bounded operations such as `pick`, `place`, `pose`, `target_pose`, and `open_drawer`. Generated programs do not directly operate the simulator. / 提供受限技能接口，生成程序不直接操作底层仿真器。

**The VLM path is not vision-only control.** Existing primitives still use actor, contact, and motion-planning information from the simulator. Deterministic environment predicates decide final task success. Visual localization, visual failure detection, and final success verification are distinct functions.

**VLM 路径不是纯视觉控制。**现有原语仍使用仿真 actor、接触信息和运动规划器；最终任务成功由确定性的环境规则判断。视觉定位、视觉失败检测与最终成功判定是三个不同环节。

## Recovery at two levels / 两层纠错

### 1. Inside a skill / 技能内部

Supported skills inspect planning results or object-position errors and make bounded local adjustments. Examples include smaller drawer-pulling steps and iterative movement toward a target position. A planned motion succeeding does not, by itself, prove that an object was securely grasped.

支持的技能会检查运动规划结果或物体位置偏差，并进行有限次数的局部调整，例如缩短抽屉拉动步长、分段逼近目标位置。规划返回成功本身不等于实际抓稳。

### 2. Repairing the program / 修正程序

An unrecoverable skill failure interrupts the current program and produces a failure report. The diagnosis agent uses the report and current scene context to guide another generation round. The runner retains the scene; it does not reset objects to hide a failed attempt. A failed final task check can also trigger this path. The default orchestration budget is three generation rounds.

技能无法局部恢复时会中断当前程序并生成失败报告，诊断 Agent 根据报告和当前场景指导下一轮生成。运行器保留场景，不通过重置物体抹去失败状态；最终任务检查未通过也可以触发这条路径。默认编排预算为三轮程序生成。

### Experimental stage feedback / 实验性阶段反馈

Opt-in VLM checks at `after_lift` and `after_place` inspect stage images for failures such as a missed grasp or incorrect placement. A detected failure can feed the program-repair path. This is stage-level observation, not continuous visual servoing or frame-by-frame control. API latency and ambiguous views must be considered when evaluating it.

可选的 VLM 检查在 `after_lift`、`after_place` 阶段观察图像，判断是否存在未抓住、未正确放置等失败，并可将检测结果送入程序修正流程。这属于阶段观察，不是连续视觉伺服或逐帧控制；评估时需要同时关注 API 延迟和视角不明确的情况。

Enable it with `--stage-feedback` in the evaluation CLI, or `stage_feedback=True` when calling `GapaRunner.run_task`. It requires a configured VLM even when object localization uses Oracle mode.

评测 CLI 使用 `--stage-feedback` 开启，调用 `GapaRunner.run_task` 时使用 `stage_feedback=True`。即使物体定位采用 Oracle 模式，阶段视觉反馈仍需配置 VLM。

Only sufficiently confident failure reports interrupt execution. An inconclusive response or VLM service error is logged and leaves the deterministic execution path in charge. The integration is experimental: unit tests establish control flow and report handling, while simulation evidence belongs in [experiments.md](experiments.md).

The enabled monitor also checks the existing 8 cm lift primitive's postcondition
using simulator object poses: height must increase by at least 3 cm relative to
the start of `pick`. A failed lift check interrupts before placing and clears the
optimistic held-object cache. This is recorded independently as
`stage_check.source=simulator_pose`; it never rewrites a visual report.
Confident camera disagreement at `after_lift` becomes `uncertain`. Missing state
is recorded as unavailable, never as a passed check. This hybrid safeguard was
added after a physical gripper-release probe exposed a wrist-camera false positive.

开启阶段监控后，也通过仿真物体位置验证已有 8 cm 抬升动作的后置条件：相对抓取开始至少升高 3 cm，否则在放置前中断。视角冲突记录为“不确定”，仿真状态验证独立标注来源，不能将这种混合检查说成纯视觉检测。高度达标也不单独证明稳定抓持，任务最终仍需通过完整环境判定。

只有置信度达到要求的失败报告会中断执行。不确定的回答或 VLM 服务错误会被记录，并继续由确定性执行流程处理。该集成属于实验功能：单元测试验证触发流程与报告处理，仿真证据单独记录在[实验页](experiments.md)。

## Memory / 记忆

The original strategy memory groups tasks into five families: placement, stacking, row arrangement, relative movement, and drawer placement. It retrieves predefined skill-sequence templates and tracks successful uses. Its original success counter did not learn a new program or tune parameters.

原有策略记忆将任务分为放置、堆叠、排列、相对移动、入柜五类，检索预置技能序列模板并累计成功使用次数。原有成功计数本身不会学习新程序或优化参数。

The experimental extension archives successful programs with task and run provenance. For a compatible atomic task and object context, it retrieves explicit skill parameters that still satisfy the current API limits. It does not replay historical coordinates, arm choices, or whole programs. Composite-program records are retained as provenance but are not treated as independently verified atomic examples. This is context-based experience reuse; any performance benefit still needs held-out evaluation with the same model, skills, and retry budget.

实验性扩展保存成功程序及其任务、运行来源。对于兼容的原子任务与物体上下文，检索仍符合当前 API 范围的显式技能参数；不重放历史坐标、机械臂选择或整个程序。复合任务的程序保留为来源记录，不当作单独验证过的原子任务示例。这属于生成上下文中的经验复用；性能收益仍需在留出场景上，以相同模型、技能库和尝试预算验证。

## Implementation map / 实现入口

| Concern / 功能 | Source / 源码 |
| --- | --- |
| Agent orchestration / Agent 编排 | [`gapa/agents/orchestrator.py`](../gapa/agents/orchestrator.py) |
| Scene lifecycle and recovery / 场景生命周期与恢复 | [`gapa/runtime/runner.py`](../gapa/runtime/runner.py) |
| Skills and local adjustments / 技能与局部调整 | [`gapa/runtime/api.py`](../gapa/runtime/api.py) |
| Localization / 视觉定位 | [`gapa/perception/providers.py`](../gapa/perception/providers.py) |
| Visual stage feedback / 视觉阶段反馈 | [`gapa/perception/feedback.py`](../gapa/perception/feedback.py) |
| Task success / 任务成功判定 | [`gapa/runtime/success.py`](../gapa/runtime/success.py) |
| Strategy and experience memory / 策略与经验记忆 | [`gapa/memory/success_memory.py`](../gapa/memory/success_memory.py) |

## Suggested GitHub About text / 建议的仓库简介

> Natural-language robot programming on RoboTwin with multi-agent skill composition, execution recovery, and experimental experience memory.

Suggested topics: `robotics`, `robotwin`, `multi-agent`, `code-generation`, `vision-language-model`, `robot-manipulation`.

This is proposed metadata only; editing this document does not change repository settings. / 此处仅提供建议文案，不会修改远端仓库设置。
