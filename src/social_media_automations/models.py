from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class User:
    id: str
    username: Optional[str]


@dataclass(frozen=True)
class Channel:
    id: str
    ig_user_id: str
    username: Optional[str]


@dataclass(frozen=True)
class Message:
    id: str
    text: str
    from_user: User
    channel: Channel
    raw: dict


@dataclass(frozen=True)
class Comment:
    id: str
    text: str
    media_id: Optional[str]
    from_user: User
    channel: Channel
    raw: dict


@dataclass(frozen=True)
class Postback:
    payload: str
    from_user: User
    channel: Channel
    raw: dict


@dataclass(frozen=True)
class Update:
    update_id: int
    type: str
    channel: Channel
    from_user: User
    message: Optional[Message]
    comment: Optional[Comment]
    postback: Optional[Postback]
    timestamp: int
    raw: dict

    @classmethod
    def from_dict(cls, d: dict) -> Optional["Update"]:
        try:
            kind = d["type"]
            ch = d["channel"]
            channel = Channel(id=ch["id"], ig_user_id=ch["ig_user_id"], username=ch.get("username"))
            f = d.get("from") or {}
            user = User(id=f.get("id", ""), username=f.get("username"))
            message = comment = postback = None
            if kind == "message":
                m = d["message"]
                message = Message(id=m["id"], text=m.get("text", ""), from_user=user, channel=channel, raw=d)
            elif kind == "comment":
                c = d["comment"]
                comment = Comment(id=c["id"], text=c.get("text", ""), media_id=c.get("media_id"),
                                  from_user=user, channel=channel, raw=d)
            elif kind == "postback":
                p = d["postback"]
                postback = Postback(payload=p.get("payload", ""), from_user=user, channel=channel, raw=d)
            else:
                return None
            return cls(update_id=d["update_id"], type=kind, channel=channel, from_user=user,
                       message=message, comment=comment, postback=postback,
                       timestamp=d.get("timestamp", 0), raw=d)
        except (KeyError, TypeError):
            return None
