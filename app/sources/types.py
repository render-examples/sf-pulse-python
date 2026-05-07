"""Source-layer types — port of bin/cron-refresh/types.ts."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

SourceName = Literal["eater", "sfist", "michelin", "funcheap", "famsf", "calacademy", "ddg"]


class RawArticle(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    source: str
    url: str
    title: str
    pub_date: str | None = Field(default=None, alias="pubDate")
    body_text: str = Field(default="", alias="bodyText")
    json_ld: Any | None = Field(default=None, alias="jsonLd")


class RssItem(BaseModel):
    title: str
    link: str = ""
    pub_date: str = ""
    description: str = ""
