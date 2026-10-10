import asyncio
import time
import uuid

from lib import util

from astrbot.api.all import AstrMessageEvent, MessageChain, Star
from astrbot.api.event import filter
from astrbot.api.message_components import File, Plain
from astrbot.core.star.context import Context

from .lib import store
from .lib.models import (
    AnyBuild,
    BuildingTask,
    ManualBuild,
    PluginConfig,
    TimerBuild,
)


class BuildArtifactCloud(Star):
    def __init__(self, context: Context, config: dict | None = None):
        store.config = PluginConfig.model_validate(config)
        self.config = store.config
        self.tasks: list[BuildingTask] = []
        self.build_finished = util.Signal[BuildingTask]()
        super().__init__(context, config)

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
                    match record:
                        case str():
                            await self.context.send_message(
                                task.caller_session,
                                MessageChain([Plain(record)]),
                            )
                        case (fp, fn):
                            await self.context.send_message(
                                task.caller_session,
                                MessageChain([File(file=fp, name=fn)]),
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

    def get_project(self, project: str) -> AnyBuild | None:
        for i in self.config.projects:
            if i.name.upper() == project.upper():
                return i
        return None
