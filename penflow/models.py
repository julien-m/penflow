"""Shared data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .context import Context, infer_role


@dataclass(slots=True)
class BBox:
    x: float = 0
    y: float = 0
    width: float = 0
    height: float = 0

    @classmethod
    def from_node(cls, data: dict[str, Any]) -> "BBox":
        return cls(
            x=float(data.get("x", 0) or 0),
            y=float(data.get("y", 0) or 0),
            width=float(data.get("width", 0) or 0),
            height=float(data.get("height", 0) or 0),
        )

    def to_dict(self) -> dict[str, float]:
        return {"x": self.x, "y": self.y, "width": self.width, "height": self.height}


@dataclass(slots=True)
class PenNode:
    id: str
    type: str
    name: str | None = None
    content: str | None = None
    context: Context = field(default_factory=Context)
    bbox: BBox = field(default_factory=BBox)
    visual: dict[str, Any] = field(default_factory=dict)
    children: list["PenNode"] = field(default_factory=list)
    parent_id: str | None = None
    order: int = 0

    @property
    def semantic_id(self) -> str | None:
        return self.context.semantic_id

    @property
    def role(self) -> str:
        return infer_role(self.type, self.context)

    def walk(self) -> list["PenNode"]:
        nodes = [self]
        for child in self.children:
            nodes.extend(child.walk())
        return nodes

    def to_expected(self) -> dict[str, Any]:
        return {
            "id": self.semantic_id or self.id,
            "pencil_id": self.id,
            "semantic_id": self.semantic_id,
            "role": self.role,
            "name": self.name,
            "text": self.content,
            "bbox": self.bbox.to_dict(),
            "visual": self.visual,
            "context": self.context.to_dict(),
            "children": [child.to_expected() for child in self.children],
        }

