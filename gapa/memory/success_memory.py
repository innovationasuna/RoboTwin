"""Strategy-level memory for GAPA.

Keep five coarse strategies, with a separate provenance archive for successes.
Only compatible, scene-independent tuning references enter generation prompts;
archived programs are never replayed or copied across scenes by this module.
"""

from __future__ import annotations

import ast
import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..domain.api_spec import API_SPECS, tuning_default_kwargs
from ..domain.objects import CABINET_SOURCE_OBJECTS, COLOR_BLOCK_OBJECTS
from ..domain.task import TaskDSL, normalize_task_dsl


STRATEGY_IDS = (
    "place_on",
    "block_stack",
    "block_row",
    "move",
    "place_in_drawer",
)


DEFAULT_STRATEGIES: tuple[dict[str, Any], ...] = (
    {
        "strategy_id": "place_on",
        "api_sequence_template": ["pose", "target_pose", "choose_arm", "pick", "place"],
        "verified_success_count": 0,
        "status": "active",
    },
    {
        "strategy_id": "block_stack",
        "api_sequence_template": [
            "pose",
            "choose_arm",
            "pick",
            "target_pose(stack_slot level=0)",
            "place",
            "pose",
            "choose_arm",
            "pick",
            "target_pose(stack_slot level=1)",
            "place",
        ],
        "verified_success_count": 0,
        "status": "active",
    },
    {
        "strategy_id": "block_row",
        "api_sequence_template": ["pose", "choose_arm", "pick", "target_pose(row_slot)", "place"],
        "verified_success_count": 0,
        "status": "active",
    },
    {
        "strategy_id": "move",
        "api_sequence_template": ["pose", "target_pose(offset)", "choose_arm", "pick", "place"],
        "verified_success_count": 0,
        "status": "active",
    },
    {
        "strategy_id": "place_in_drawer",
        "api_sequence_template": ["pose(source)", "choose_arm", "opposite_arm", "open_drawer", "pose(source)", "choose_arm", "pick", "target_pose", "place"],
        "verified_success_count": 0,
        "status": "active",
    },
)

STRATEGY_TUNING_METHODS: dict[str, tuple[str, ...]] = {
    "place_on": ("pick", "place"),
    "block_stack": ("pick", "place"),
    "block_row": ("pick", "place"),
    "move": ("pick", "place"),
    "place_in_drawer": ("open_drawer", "pick", "place"),
}

STRATEGY_TUNING_OVERRIDES: dict[str, dict[str, dict[str, Any]]] = {
    "place_in_drawer": {
        "place": {"pre_dis": 0.13, "dis": 0.1},
    },
}


def strategy_id_for_task(task: TaskDSL) -> str | None:
    # 功能：执行 strategy id for task 相关的业务逻辑，并把结果整理给调用方继续使用。
    # 参数：task：标准化 TaskDSL 任务对象，描述目标物体、关系和约束。
    # 返回：返回 str | None 类型结果；调用方依赖该结构继续执行或生成诊断输出。
    """Map a canonical TaskDSL to one of the fixed strategy ids."""

    task = normalize_task_dsl(task)
    if task.task_type == "composite":
        return None
    if task.intent == "arrange":
        if task.pattern == "stack":
            return "block_stack"
        if task.pattern == "row":
            return "block_row"
        return None
    if task.intent == "move":
        return "move"
    if task.intent != "place":
        return None
    if task.target_name == "cabinet" and task.relation == "in":
        if task.object_name in CABINET_SOURCE_OBJECTS:
            return "place_in_drawer"
        return None
    if task.relation == "in":
        return None
    if task.relation == "on":
        if task.object_name in COLOR_BLOCK_OBJECTS and task.target_name in COLOR_BLOCK_OBJECTS:
            return "block_stack"
        return "place_on"
    return None


@dataclass
class SuccessMemoryManager:
    root: Path

    @property
    def success_dir(self) -> Path:
        # 功能：生成或读取成功经验相关标识和提示，辅助后续任务复用；该方法属于 SuccessMemoryManager，会复用该类维护的上下文。。
        # 参数：self：当前类实例，提供内部状态和依赖对象。
        # 返回：返回 Path 类型结果；调用方依赖该结构继续执行或生成诊断输出。
        return self.root / "success"

    @property
    def jsonl_path(self) -> Path:
        # 功能：执行 JSONL path 相关的业务逻辑，并把结果整理给调用方继续使用。
        # 参数：self：当前类实例，提供内部状态和依赖对象。
        # 返回：返回 Path 类型结果；调用方依赖该结构继续执行或生成诊断输出。
        return self.success_dir / "success_memory.jsonl"

    @property
    def episodes_path(self) -> Path:
        return self.success_dir / "success_episodes.jsonl"

    def retrieve_strategy(self, task: TaskDSL) -> list[dict[str, Any]]:
        # 功能：执行 retrieve strategy 相关的业务逻辑，并把结果整理给调用方继续使用。
        # 参数：self：当前类实例，提供内部状态和依赖对象；task：标准化 TaskDSL 任务对象，描述目标物体、关系和约束。
        # 返回：返回 list[dict[str, Any]] 类型结果；调用方依赖该结构继续执行或生成诊断输出。
        if task.task_type == "composite":
            seen: set[str] = set()
            result: list[dict[str, Any]] = []
            for sub_task in task.sub_tasks:
                for item in self.retrieve_strategy(sub_task):
                    strategy_id = str(item.get("strategy_id", ""))
                    if strategy_id and strategy_id not in seen:
                        seen.add(strategy_id)
                        result.append(item)
            return result

        strategy_id = strategy_id_for_task(task)
        if strategy_id is None:
            return []
        return [
            item
            for item in self._read_strategy_items()
            if item.get("strategy_id") == strategy_id and item.get("status") == "active"
        ]

    def retrieve_exact(self, task: TaskDSL) -> list[dict[str, Any]]:
        # 功能：执行 retrieve exact 相关的业务逻辑，并把结果整理给调用方继续使用。
        # 参数：self：当前类实例，提供内部状态和依赖对象；task：标准化 TaskDSL 任务对象，描述目标物体、关系和约束。
        # 返回：返回 list[dict[str, Any]] 类型结果；调用方依赖该结构继续执行或生成诊断输出。
        """Compatibility alias; returns strategy memory, not exact task memory."""

        return self.retrieve_strategy(task)

    def prompt_for(self, task: TaskDSL) -> str:
        # 功能：生成面向 LLM 或 VLM 的提示词，明确输入格式和输出约束；该方法属于 SuccessMemoryManager，会复用该类维护的上下文。。
        # 参数：self：当前类实例，提供内部状态和依赖对象；task：标准化 TaskDSL 任务对象，描述目标物体、关系和约束。
        # 返回：返回 str 类型结果；调用方依赖该结构继续执行或生成诊断输出。
        items = self.retrieve_strategy(task)
        if not items:
            return "None."
        prompt = self._prompt_for_items(items, title="# Strategy Memory", subtitle="## Relevant Strategies")
        examples = self.retrieve_tuning_examples(task)
        if examples:
            prompt += "\n\n## Compatible successful-program tuning references\n"
            prompt += (
                "These are explicit parameters declared in successful atomic programs, "
                "not per-call telemetry or guarantees for a new scene. Re-localize all "
                "objects with api.pose / api.target_pose and choose arms from the current "
                "scene; never replay historical coordinates, arm choices, or source code. "
                "Treat these values as optional starting points within the API limits.\n"
            )
            for index, example in enumerate(examples, start=1):
                prompt += f"- Reference {index}: `{json.dumps(example['tuning_calls'], ensure_ascii=False)}`\n"
        return prompt

    def retrieve_tuning_examples(self, task: TaskDSL, limit: int = 3) -> list[dict[str, Any]]:
        """Return recent atomic successes for the same task and object context.

        Strategy templates remain transferable between objects. Learned distances
        are deliberately stricter: a cup's grasp parameters do not transfer to a
        bowl, and a full composite program is not an independently tested subtask.
        """
        if limit <= 0 or not self.episodes_path.exists():
            return []
        task = normalize_task_dsl(task)
        tasks = task.sub_tasks if task.is_composite else [task]
        compatible = {json.dumps(item.canonical_dict(), sort_keys=True) for item in tasks}
        result: list[dict[str, Any]] = []
        for line in reversed(self.episodes_path.read_text(encoding="utf-8").splitlines()):
            if not line.strip():
                continue
            episode = json.loads(line)
            if episode.get("verification_scope") != "atomic_task_success":
                continue
            if json.dumps(episode.get("task"), sort_keys=True) not in compatible:
                continue
            # Re-extract using today's API whitelist/ranges, not stale persisted
            # parameters if the API specification has changed since recording.
            episode_task = TaskDSL.from_dict(episode["task"])
            tuning_calls = _extract_tuning_calls(episode.get("source", ""), episode_task)
            if not tuning_calls:
                continue
            result.append({
                "strategy_id": episode["strategy_id"],
                "run_id": episode["run_id"],
                "recorded_at": episode["recorded_at"],
                "task": episode["task"],
                "tuning_calls": tuning_calls,
            })
            if len(result) >= limit:
                break
        return result

    def record_success(
        self,
        task: TaskDSL,
        source: str,
        run_id: str,
        instruction: str,
        parent_run_id: str | None = None,
        subtask_index: int | None = None,
    ) -> None:
        # 功能：记录执行过程中的状态、轨迹或感知结果，便于回放和诊断；该方法属于 SuccessMemoryManager，会复用该类维护的上下文。。
        # 参数：self：当前类实例，提供内部状态和依赖对象；task：标准化 TaskDSL 任务对象，描述目标物体、关系和约束；source：待校验、重放或分析的 Python 源码文本；run_id：运行编号，用于读取历史结果或构造公开路径；instruction：用户输入的自然语言任务指令；parent_run_id：parent run id 输入，类型约束为 str | None，默认值为 None；subtask_index：subtask index 输入，类型约束为 int | None，默认值为 None。
        # 返回：无返回值；通过副作用更新环境、文件、对象状态或在失败时抛出异常。
        # The caller owns success verification. A subtask record from the current
        # orchestrator contains its parent's complete program, not an isolated
        # successful subprogram; archive it without extracting tuning examples.
        task = normalize_task_dsl(task)
        strategy_id = strategy_id_for_task(task)
        if strategy_id is None:
            return
        now = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
        from_composite = parent_run_id is not None or subtask_index is not None
        episode = {
            "schema_version": 1,
            "strategy_id": strategy_id,
            "recorded_at": now,
            "task": task.canonical_dict(),
            "instruction": instruction,
            "run_id": run_id,
            "parent_run_id": parent_run_id,
            "subtask_index": subtask_index,
            "verification_scope": "parent_composite_success" if from_composite else "atomic_task_success",
            "source_scope": "whole_parent_program" if from_composite else "atomic_program",
            "source": source,
            "tuning_calls": [] if from_composite else _extract_tuning_calls(source, task),
        }
        self.success_dir.mkdir(parents=True, exist_ok=True)
        with self.episodes_path.open("a", encoding="utf-8") as archive:
            archive.write(json.dumps(episode, ensure_ascii=False) + "\n")
        items = self._read_strategy_items()
        for item in items:
            if item.get("strategy_id") == strategy_id:
                item["verified_success_count"] = int(item.get("verified_success_count", 0)) + 1
                item["last_success_at"] = now
                break
        self._write_all(items)

    def _read_strategy_items(self) -> list[dict[str, Any]]:
        # 功能：读取内部缓存或持久化数据，并在异常或缺失时提供兼容处理；该方法属于 SuccessMemoryManager，会复用该类维护的上下文。。
        # 参数：self：当前类实例，提供内部状态和依赖对象。
        # 返回：返回 list[dict[str, Any]] 类型结果；调用方依赖该结构继续执行或生成诊断输出。
        defaults = {item["strategy_id"]: self._clean_strategy_item(item) for item in DEFAULT_STRATEGIES}
        if self.jsonl_path.exists():
            for line in self.jsonl_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                item = json.loads(line)
                strategy_id = item.get("strategy_id")
                if strategy_id in defaults:
                    merged = dict(defaults[strategy_id])
                    for key in ("api_sequence_template", "verified_success_count", "last_success_at", "status"):
                        if key in item:
                            merged[key] = item[key]
                    defaults[strategy_id] = self._clean_strategy_item(merged)
        return [defaults[strategy_id] for strategy_id in STRATEGY_IDS]

    def _write_all(self, items: list[dict[str, Any]]) -> None:
        # 功能：把内部运行结果写入文件或缓存，统一处理路径和序列化细节；该方法属于 SuccessMemoryManager，会复用该类维护的上下文。。
        # 参数：self：当前类实例，提供内部状态和依赖对象；items：items 输入，类型约束为 list[dict[str, Any]]。
        # 返回：无返回值；通过副作用更新环境、文件、对象状态或在失败时抛出异常。
        self.success_dir.mkdir(parents=True, exist_ok=True)
        ordered = []
        by_id = {item.get("strategy_id"): item for item in items}
        for strategy_id in STRATEGY_IDS:
            if strategy_id in by_id:
                ordered.append(self._clean_strategy_item(by_id[strategy_id]))
        text = "\n".join(json.dumps(item, ensure_ascii=False) for item in ordered)
        self.jsonl_path.write_text(text + ("\n" if text else ""), encoding="utf-8")

    def _clean_strategy_item(self, item: dict[str, Any]) -> dict[str, Any]:
        # 功能：处理内部辅助逻辑 clean strategy item，把重复的边界检查、状态整理或转换流程集中在一处。
        # 参数：self：当前类实例，提供内部状态和依赖对象；item：item 输入，类型约束为 dict[str, Any]。
        # 返回：返回 dict[str, Any] 类型结果；调用方依赖该结构继续执行或生成诊断输出。
        strategy_id = str(item["strategy_id"])
        sequence = item.get("api_sequence_template") or []
        cleaned: dict[str, Any] = {
            "strategy_id": strategy_id,
            "api_sequence_template": [str(step) for step in sequence],
            "default_tuning_kwargs": self._default_tuning_kwargs_for_strategy(strategy_id),
            "verified_success_count": int(item.get("verified_success_count", 0) or 0),
            "status": str(item.get("status") or "active"),
        }
        if item.get("last_success_at"):
            cleaned["last_success_at"] = str(item["last_success_at"])
        return cleaned

    def _prompt_for_items(self, items: list[dict[str, Any]], title: str, subtitle: str) -> str:
        # 功能：拼接内部提示词模板，把任务、场景和约束整理给模型使用；该方法属于 SuccessMemoryManager，会复用该类维护的上下文。。
        # 参数：self：当前类实例，提供内部状态和依赖对象；items：items 输入，类型约束为 list[dict[str, Any]]；title：title 输入，类型约束为 str；subtitle：subtitle 输入，类型约束为 str。
        # 返回：返回 str 类型结果；调用方依赖该结构继续执行或生成诊断输出。
        lines = [
            title, "",
            "Always re-localize objects and recompute target poses and arm choices "
            "for the current scene. Strategy counts may include successful parent "
            "composite runs; only atomic successes supply tuning references.",
            "", subtitle,
        ]
        for item in items:
            lines.extend([
                "",
                f"### {item.get('strategy_id')}",
                f"- API sequence template: `{' -> '.join(item.get('api_sequence_template', []))}`",
                f"- Default tuning kwargs to copy explicitly: `{self._format_default_tuning_kwargs(item)}`",
                f"- Verified success count: `{int(item.get('verified_success_count', 0))}`",
            ])
        return "\n".join(lines)

    def _default_tuning_kwargs_for_strategy(self, strategy_id: str) -> dict[str, dict[str, Any]]:
        # 功能：处理内部辅助逻辑 default tuning kwargs for strategy，把重复的边界检查、状态整理或转换流程集中在一处。
        # 参数：self：当前类实例，提供内部状态和依赖对象；strategy_id：strategy id 输入，类型约束为 str。
        # 返回：返回 dict[str, dict[str, Any]] 类型结果；调用方依赖该结构继续执行或生成诊断输出。
        defaults = {
            method: tuning_default_kwargs(method)
            for method in STRATEGY_TUNING_METHODS.get(strategy_id, ())
            if tuning_default_kwargs(method)
        }
        for method, overrides in STRATEGY_TUNING_OVERRIDES.get(strategy_id, {}).items():
            method_defaults = dict(defaults.get(method, {}))
            method_defaults.update(overrides)
            defaults[method] = method_defaults
        return defaults

    def _format_default_tuning_kwargs(self, item: dict[str, Any]) -> str:
        # 功能：格式化内部诊断、提示或默认参数，保持输出风格一致；该方法属于 SuccessMemoryManager，会复用该类维护的上下文。。
        # 参数：self：当前类实例，提供内部状态和依赖对象；item：item 输入，类型约束为 dict[str, Any]。
        # 返回：返回 str 类型结果；调用方依赖该结构继续执行或生成诊断输出。
        defaults = item.get("default_tuning_kwargs")
        if not isinstance(defaults, dict):
            defaults = self._default_tuning_kwargs_for_strategy(str(item.get("strategy_id") or ""))
        parts = []
        for method, kwargs in defaults.items():
            if not isinstance(kwargs, dict) or not kwargs:
                continue
            rendered = ", ".join(f"{key}={value!r}" for key, value in kwargs.items())
            parts.append(f"api.{method}({rendered})")
        return "; ".join(parts) if parts else "None"


def _extract_tuning_calls(source: str, task: TaskDSL) -> list[dict[str, Any]]:
    """Extract literal, in-range grasp/place/drawer parameters, never poses.

    Values belong to their specific calls and object contexts. We do not flatten
    multiple calls into a single method dictionary (which could mix stack levels
    or objects), infer dynamic values, or execute archived source.
    """
    strategy_id = strategy_id_for_task(task)
    methods = STRATEGY_TUNING_METHODS.get(strategy_id, ())
    try:
        tree = ast.parse(source)
    except (SyntaxError, TypeError):
        return []
    objects = set(task.object_names) if task.intent == "arrange" else {task.object_name}
    targets = objects | {"table"} if task.intent == "arrange" else {task.target_name}
    result = []
    for call in sorted((node for node in ast.walk(tree) if isinstance(node, ast.Call)), key=lambda node: node.lineno):
        if not (
            isinstance(call.func, ast.Attribute)
            and isinstance(call.func.value, ast.Name)
            and call.func.value.id == "api"
            and call.func.attr in methods
        ):
            continue
        method = call.func.attr
        spec = API_SPECS[method]
        args = dict(zip(spec.parameter_names, call.args))
        args.update({kw.arg: kw.value for kw in call.keywords if kw.arg is not None})

        def literal(name: str) -> Any:
            try:
                return ast.literal_eval(args[name])
            except (KeyError, ValueError, TypeError, SyntaxError):
                return None

        object_name = literal("cabinet" if method == "open_drawer" else "name")
        if method == "open_drawer":
            if object_name != "cabinet" or task.target_name != "cabinet":
                continue
        elif not isinstance(object_name, str) or object_name not in objects:
            continue
        context = {"object_name": object_name}
        if method == "place":
            target_name, relation = literal("target_name"), literal("relation")
            expected_relation = "on" if task.intent == "arrange" else task.relation
            if not isinstance(target_name, str) or target_name not in targets or relation != expected_relation:
                continue
            context.update(target_name=target_name, relation=relation)
        kwargs = {}
        for parameter in spec.parameters:
            if not parameter.tuning or parameter.name not in args:
                continue
            value = literal(parameter.name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                continue
            if parameter.has_range() and not parameter.min_value <= value <= parameter.max_value:
                continue
            if isinstance(parameter.default, int) and not isinstance(value, int):
                continue
            kwargs[parameter.name] = value
        if kwargs:
            result.append({"api": method, **context, "kwargs": kwargs})
    return result


def extract_api_sequence(source: str) -> list[str]:
    # 功能：从源码、响应或记录中提取关键结构化信息。
    # 参数：source：待校验、重放或分析的 Python 源码文本。
    # 返回：返回 list[str] 类型结果；调用方依赖该结构继续执行或生成诊断输出。
    """Compatibility helper for tests and old imports."""

    tree = ast.parse(source)
    sequence: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            value = node.func.value
            if isinstance(value, ast.Name) and value.id == "api":
                sequence.append(node.func.attr)
    return sequence
