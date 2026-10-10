import asyncio
import time
import uuid

from astrbot.api.all import AstrMessageEvent, Star
from astrbot.api.event import filter
from astrbot.api.message_components import File
from astrbot.core.star.context import Context

from .lib import store
from .lib.models import AnyBuild, BuildingTask, ManualBuild, PluginConfig, TaskState


class BuildArtifactCloud(Star):
    def __init__(self, context: Context, config: dict | None = None):
        super().__init__(context, config)
        store.config = PluginConfig.model_validate(config)
        self.config = store.config
        self.tasks: list[BuildingTask] = []
        self.building: bool = False

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
                f"- {x.name}：{x.description}" for x in self.config.projects
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
        # 创建任务加入队列
        task = BuildingTask(
            project=prj,
            id=uuid.uuid4(),
            spawn=time.time(),
            state=TaskState.QUEUED,
        )
        self.tasks.append(task)
        # 把回复用户的工作全权交给用户调用命令的地方，事件循环和任务和这个进行一个解耦
        # 开始事件循环，如果已经正在循环了他会自己退出
        async for i in self.eventloop():
            match i:
                # 迭代出字符串是日志，返回给用户
                case str():
                    yield event.plain_result(i)
                # 迭代出文件地址和文件名，发送产物
                case (fp, fn):
                    yield event.chain_result([File(file=fp, name=fn)])

    async def eventloop(self):
        if self.building:
            return
        self.building = True
        # 重复直到清空任务队列
        while len(self.tasks) > 0:
            task = self.tasks.pop()
            match task.project:
                case ManualBuild():
                    # 把任务过程迭代出的输出再迭代出去
                    async for i in task.run():
                        yield i
            # 给1秒的冷却，防止卡死主事件循环
            await asyncio.sleep(1)
        self.building = False

    def get_project(self, project: str) -> AnyBuild | None:
        for i in self.config.projects:
            if i.name.upper() == project.upper():
                return i
        return None
