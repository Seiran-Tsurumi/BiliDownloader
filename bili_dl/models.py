"""对外数据模型。"""
from dataclasses import dataclass


@dataclass
class VideoMeta:
    bvid: str
    aid: int
    cid: int
    title: str
    owner_name: str
    duration: int


@dataclass
class Quality:
    qn: int
    desc: str


__all__ = ["VideoMeta", "Quality"]
