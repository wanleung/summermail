from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Email:
    id: str
    thread_id: str
    subject: str
    sender_email: str
    sender_name: str
    received_at: datetime
    body_text: str
    labels: list = field(default_factory=list)
    is_read: bool = False
    fetched_at: Optional[datetime] = None


@dataclass
class EmailScore:
    email_id: str
    vip_match: bool = False
    keyword_score: int = 0
    llm_score: int = 0
    total_score: int = 0
    llm_reasoning: str = ""
    scored_at: Optional[datetime] = None


@dataclass
class Summary:
    date: str
    summary_text: str
    email_count: int
    top_email_ids: list = field(default_factory=list)
    sent_at: Optional[datetime] = None
    sent_to: str = ""
    id: Optional[int] = None


@dataclass
class VipSender:
    pattern: str
    label: str = ""
    id: Optional[int] = None


@dataclass
class Keyword:
    keyword: str
    weight: int = 5
    match_body: bool = True
    id: Optional[int] = None
