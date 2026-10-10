import asyncio
import enum
import os
from uuid import UUID

from pydantic import BaseModel

from astrbot.api import logger
from astrbot.api.star import StarTools

from . import async_zip


class BaseBuild(BaseModel):
    name: str
    description: str
    path: str
    build: str
    dist: str
    compress: bool


class ManualBuild(BaseBuild):
    allow_parallax: bool


class TimerBuild(BaseBuild):
    gap: float
    session: str


AnyBuild = ManualBuild | TimerBuild


class PluginConfig(BaseModel):
    projects: list[AnyBuild]


class TaskState(enum.Enum):
    QUEUED = 0
    RUNNING = 1
    FINISHED = 2


class BuildingTask(BaseModel):
    project: AnyBuild
    id: UUID
    spawn: float
    state: TaskState

    async def run(self):
        yield f"🔨 任务ID {self.id} 开始编译：{self.project.name}。"
        cwd = os.getcwd()
        os.chdir(self.project.path)
        try:
            await asyncio.create_subprocess_shell(self.project.build, shell=True)
        except Exception as e:
            logger.error(e)
            yield f"💔 任务ID {self.id} 已失败，请检查控制台。"
        yield f"🎯 任务ID {self.id} 编译成功。"
        if self.project.compress:
            yield "📦 正在压缩产物，请稍等..."
            fp = str(
                StarTools.get_data_dir("astrbot_plugin_build_artifact")
                / f"{self.id}.zip"
            )
            await async_zip.compress(self.project.dist, fp)
            yield (fp, f"[{self.project.name}] {os.path.basename(fp)}")
        else:
            yield f"📦 以下是 {self.id} 的产物："
            if os.path.isdir(self.project.dist):
                for root, _, files in os.walk(self.project.dist):
                    for fn in files:
                        yield (os.path.join(root, fn), fn)
        os.chdir(cwd)
