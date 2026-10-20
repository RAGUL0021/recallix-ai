"""INTEGRATION TEST against your real Supabase project. Skipped unless these env vars are set:
  SUPABASE_URL, SUPABASE_ANON_KEY, TEST_USER_A_EMAIL, TEST_USER_A_PASSWORD, TEST_USER_B_EMAIL, TEST_USER_B_PASSWORD
Create two verified test users first (Supabase Dashboard -> Authentication -> Add user, tick 'Auto confirm')."""
import os
import uuid

import pytest
from supabase import create_client

NEEDED = ["SUPABASE_URL", "SUPABASE_ANON_KEY", "TEST_USER_A_EMAIL", "TEST_USER_A_PASSWORD",
          "TEST_USER_B_EMAIL", "TEST_USER_B_PASSWORD"]
pytestmark = pytest.mark.skipif(any(not os.environ.get(k) for k in NEEDED), reason="Supabase test env not set")


def _login(prefix):
    c = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_ANON_KEY"])
    r = c.auth.sign_in_with_password({"email": os.environ[f"TEST_USER_{prefix}_EMAIL"],
                                      "password": os.environ[f"TEST_USER_{prefix}_PASSWORD"]})
    return c, r.user.id


@pytest.fixture(scope="module")
def users():
    (a, aid), (b, bid) = _login("A"), _login("B")
    doc = a.table("documents").insert({
        "owner_id": aid, "original_name": "private.txt", "file_type": "text", "size_bytes": 5,
        "storage_path": f"{aid}/{uuid.uuid4().hex}.txt", "sha256": uuid.uuid4().hex}).execute().data[0]
    conv = a.table("conversations").insert({"owner_id": aid, "document_id": doc["id"], "title": "secret"}).execute().data[0]
    a.table("messages").insert({"conversation_id": conv["id"], "owner_id": aid, "role": "user", "content": "secret"}).execute()
    a.table("document_chunks").insert({"document_id": doc["id"], "owner_id": aid, "chunk_index": 0,
                                       "page_number": 1, "content": "secret text"}).execute()
    a.storage.from_("documents").upload(doc["storage_path"], b"hello", {"content-type": "text/plain"})
    yield a, aid, b, bid, doc, conv
    a.storage.from_("documents").remove([doc["storage_path"]])
    a.table("documents").delete().eq("id", doc["id"]).execute()
    a.table("conversations").delete().eq("id", conv["id"]).execute()


def test_b_cannot_read_a_rows(users):
    a, aid, b, bid, doc, conv = users
    for table in ["documents", "conversations", "messages", "document_chunks", "saved_answers", "usage_events"]:
        rows = b.table(table).select("*").execute().data
        assert all(r.get("owner_id") == bid for r in rows), table
    assert b.table("documents").select("id").eq("id", doc["id"]).execute().data == []
    assert b.table("profiles").select("id").eq("id", aid).execute().data == []


def test_b_cannot_write_as_a(users):
    a, aid, b, bid, doc, conv = users
    with pytest.raises(Exception):
        b.table("documents").insert({"owner_id": aid, "original_name": "x", "file_type": "text", "size_bytes": 1,
                                     "storage_path": f"{aid}/x.txt", "sha256": uuid.uuid4().hex}).execute()
    with pytest.raises(Exception):  # message into A's conversation
        b.table("messages").insert({"conversation_id": conv["id"], "owner_id": bid, "role": "user", "content": "x"}).execute()
    assert b.table("documents").update({"original_name": "pwned"}).eq("id", doc["id"]).execute().data == []
    assert b.table("documents").delete().eq("id", doc["id"]).execute().data == []


def test_b_cannot_use_vector_search_on_a_doc(users):
    a, aid, b, bid, doc, conv = users
    res = b.rpc("match_chunks", {"query_embedding": [0.0] * 768, "p_document_id": doc["id"], "match_count": 5}).execute()
    assert res.data == []


def test_storage_isolation(users):
    a, aid, b, bid, doc, conv = users
    assert a.storage.from_("documents").download(doc["storage_path"]) == b"hello"
    with pytest.raises(Exception):
        b.storage.from_("documents").download(doc["storage_path"])
    with pytest.raises(Exception):
        b.storage.from_("documents").upload(f"{aid}/evil.txt", b"x", {"content-type": "text/plain"})


def test_usage_events_cannot_be_reset(users):
    a, aid, b, bid, doc, conv = users
    a.table("usage_events").insert({"owner_id": aid, "kind": "ai_chat", "units": 1}).execute()
    assert a.table("usage_events").delete().eq("owner_id", aid).execute().data == []
