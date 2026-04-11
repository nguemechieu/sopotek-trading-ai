from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class TerminalCommandRequest(BaseModel):
    command: str = Field(min_length=1, max_length=512)
    terminal_id: str | None = Field(default=None, max_length=160)


class TerminalAssistantResponse(BaseModel):
    headline: str
    confidence: str
    reason: str
    risk_level: str
    expected_duration: str


class TerminalCommandParameterSpec(BaseModel):
    name: str
    summary: str
    required: bool = False
    default: str | None = None
    choices: list[str] = Field(default_factory=list)


class TerminalCommandSpec(BaseModel):
    command: str
    summary: str
    example: str
    permission: str = "viewer"
    parameters: list[TerminalCommandParameterSpec] = Field(default_factory=list)


class TerminalSessionSpec(BaseModel):
    terminal_id: str
    label: str
    summary: str
    kind: str = "execution"
    broker_label: str = ""
    account_label: str = ""
    mode: str = "paper"
    launch_href: str = ""
    primary: bool = False


class TerminalCommandResponse(BaseModel):
    command_id: str
    terminal_id: str
    command: str
    status: str
    message: str
    lines: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    data: dict = Field(default_factory=dict)
    assistant: TerminalAssistantResponse | None = None
    timestamp: datetime


class TerminalManifestResponse(BaseModel):
    active_terminal_id: str = ""
    active_terminal_label: str = ""
    workspace_key: str = ""
    broker_label: str = ""
    account_label: str = ""
    mode: str = "paper"
    terminals: list[TerminalSessionSpec] = Field(default_factory=list)
    commands: list[TerminalCommandSpec] = Field(default_factory=list)
    banners: list[str] = Field(default_factory=list)
    examples: list[str] = Field(default_factory=list)
    desktop_defaults: dict = Field(default_factory=dict)
