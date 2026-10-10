import asyncio
import os
import time
from abc import ABC, abstractmethod
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from astrbot.api.all import logger
from astrbot.api.star import StarTools

from . import util


class BaseBuild(BaseModel, ABC):
    enable: bool
    name: str
    description: str
    path: str
    build: str
    dist: str
    compress: bool

    @staticmethod
    @abstractmethod
    def icon() -> str:
        pass


class ManualBuild(BaseBuild):
    allow_parallax: bool

    @staticmethod
    def icon() -> str:
        return "🔨"


class TimerBuild(BaseBuild):
    gap: float
    session: str
    last_finished_in: float = Field(default=0)

    def flag(self) -> bool:
        if not self.is_cooldowned():
            return False
        self.last_finished_in = time.time()
        return True

    def is_cooldowned(self) -> bool:
        return time.time() - self.last_finished_in > self.gap

    @staticmethod
    def icon() -> str:
        return "⏰️"


AnyBuild = ManualBuild | TimerBuild


class PluginConfig(BaseModel):
    projects: list[AnyBuild]
    allow_call_timer: bool
    timer_gap: float
    eventloop_gap: float


class BuildingTask(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    project: AnyBuild
    id: UUID
    spawn: float
    caller_session: str

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
            yield "📦 正在打包产物，请稍等..."
            fp = str(
                StarTools.get_data_dir("astrbot_plugin_build_artifact")
                / f"{self.id}.zip"
            )
            await util.compress(self.project.dist, fp)
            yield (fp, f"[{self.project.name}] {os.path.basename(fp)}")
        else:
            yield f"📦 以下是 {self.id} 的产物："
            if os.path.isdir(self.project.dist):
                for root, _, files in os.walk(self.project.dist):
                    for fn in files:
                        yield (os.path.join(root, fn), fn)
        os.chdir(cwd)
