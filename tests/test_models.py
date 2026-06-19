from social_media_automations.models import Update, Message, Comment, Postback

MSG = {
    "update_id": 7, "type": "message",
    "channel": {"id": "ch-1", "ig_user_id": "178", "username": "salon"},
    "from": {"id": "igsid-9", "username": "shopper"},
    "message": {"id": "mid-7", "text": "can I book?"},
    "timestamp": 1718800000000,
}
CMT = {
    "update_id": 8, "type": "comment",
    "channel": {"id": "ch-1", "ig_user_id": "178", "username": "salon"},
    "from": {"id": "u1", "username": None},
    "comment": {"id": "c-77", "text": "price?", "media_id": "m-5"},
    "timestamp": 1718800001000,
}
PB = {
    "update_id": 9, "type": "postback",
    "channel": {"id": "ch-1", "ig_user_id": "178", "username": "salon"},
    "from": {"id": "u1", "username": "x"},
    "postback": {"payload": "book"},
    "timestamp": 1718800002000,
}


def test_parses_message_update():
    u = Update.from_dict(MSG)
    assert u.update_id == 7 and u.type == "message"
    assert isinstance(u.message, Message)
    assert u.message.id == "mid-7" and u.message.text == "can I book?"
    assert u.from_user.username == "shopper"
    assert u.channel.id == "ch-1"
    assert u.comment is None and u.postback is None
    assert u.raw is MSG


def test_parses_comment_update():
    u = Update.from_dict(CMT)
    assert isinstance(u.comment, Comment)
    assert u.comment.id == "c-77" and u.comment.media_id == "m-5"
    assert u.message is None


def test_parses_postback_update():
    u = Update.from_dict(PB)
    assert isinstance(u.postback, Postback)
    assert u.postback.payload == "book"


def test_unknown_type_returns_none():
    assert Update.from_dict({"update_id": 1, "type": "reaction"}) is None


def test_malformed_returns_none():
    assert Update.from_dict({"nope": True}) is None
