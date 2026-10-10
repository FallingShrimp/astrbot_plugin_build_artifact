import asyncio
import os
import time
import uuid

from astrbot.api.all import AstrMessageEvent, MessageChain, Star, logger
from astrbot.api.event import filter
from astrbot.api.message_components import File, Plain
from astrbot.core.star.context import Context

from .lib import util
from .lib.models import (
    AnyBuild,
    BuildingTask,
    ManualBuild,
    PluginConfig,
    TimerBuild,
)


class BuildArtifactCloud(Star):
    def __init__(self, context: Context, config: dict | None = None):
        self.config = PluginConfig.model_validate(config)
        self.tasks: list[BuildingTask] = []
        self.build_finished = util.Signal[BuildingTask]()
        asyncio.create_task(self.validate_config())
        super().__init__(context, config)

    async def validate_config(self):
        if self.config:
            if self.config.timer_gap <= 0 or self.config.eventloop_gap <= 0:
                logger.warning(
                    "不推荐令轮询的间隔小于或等于0，可能会卡死AstrBot的事件循环"
                )
            for project in self.config.projects:
                if not project.enable:
                    continue
                if os.path.isdir(project.path):
                    pass
                else:
                    logger.error(f"[{project.name}] 的工作目录不存在或并非一个目录")
                match project:
                    case TimerBuild():
                        if project.gap <= 0:
                            logger.warning(
                                f"{project.name}的推送间隔太短，可能造成刷屏！！！"
                            )

    async def initialize(self):
        self.eventlooping: bool = True
        self.el = asyncio.create_task(self.eventloop())
        self.poll_timing: bool = True
        self.pt = asyncio.create_task(self.poll_timer())

    async def terminate(self):
        self.eventlooping = False
        self.poll_timing = False

    @filter.command(
        "list",
        alias={
            "项目列表",
            "列表",
            "projects",
        },
    )
    async def list(self, event: AstrMessageEvent):
        if len(self.config.projects) == 0:
            yield event.plain_result("当前没有配置任何项目。")
        else:
            listed = "\n".join(
                f"- {type(x).icon()}{x.name}：{x.description}"
                for x in self.config.projects
            )
            yield event.plain_result(f"项目列表：\n{listed}")

    @filter.command(
        "build",
        alias={
            "构建",
            "编译",
            "生成",
            "给我",
            "giveme",
            "provide",
            "generate",
        },
    )
    async def build(self, event: AstrMessageEvent, project: str):
        """手动触发构建"""
        prj = self.get_project(project)
        if not prj:
            yield event.plain_result(
                f"不存在名为“{project}”的已配置项目，请使用list命令查看"
            )
            return
        if not prj.enable:
            yield event.plain_result("💔 该任务已被禁用")
        match prj:
            case ManualBuild():
                asyncio.create_task(self.task(prj, event.unified_msg_origin))
            case TimerBuild():
                if self.config.allow_call_timer:
                    asyncio.create_task(self.task(prj, event.unified_msg_origin))
                else:
                    yield event.plain_result("💔 定时构建任务不可以被手动调用")

    async def eventloop(self):
        while self.eventlooping:
            if len(self.tasks) > 0:
                task = self.tasks.pop()
                async for record in task.run():
                    sent = False
                    match record:
                        case str():
                            sent = await self.context.send_message(
                                task.caller_session,
                                MessageChain([Plain(record)]),
                            )
                        case (fp, fn):
                            sent = await self.context.send_message(
                                task.caller_session,
                                MessageChain([File(file=fp, name=fn)]),
                            )
                    if not sent:
                        logger.error(
                            f"会话UMO {task.caller_session} 无效，产物&日志发布失败"
                        )
                    self.build_finished.emit(task)
            await asyncio.sleep(self.config.eventloop_gap)

    async def poll_timer(self):
        while self.poll_timing:
            for project in self.config.projects:
                match project:
                    case TimerBuild():
                        can = True
                        if not project.enable:
                            can = False
                        for task in self.tasks:
                            if task.project == project:
                                can = False
                                break
                        if can and project.is_cooldowned():
                            asyncio.create_task(self.task(project, project.session))
            await asyncio.sleep(self.config.timer_gap)

    async def task(self, project: AnyBuild, session: str):
        task = BuildingTask(
            project=project,
            id=uuid.uuid4(),
            spawn=time.time(),
            caller_session=session,
        )
        self.tasks.append(task)
        while await self.build_finished.connect() != task:
            pass
        match project:
            case TimerBuild():
                project.flag()

    def get_project(self, project: str) -> AnyBuild | None:
        for i in self.config.projects:
            if i.name.upper() == project.upper():
                return i
        return None
