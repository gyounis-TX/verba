"""Tests for the SQLite Database class."""

import tempfile
import os

import pytest

from storage.database import Database


@pytest.fixture
def db():
    """Create an isolated Database using a temp file."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        yield Database(db_path=path)
    finally:
        os.unlink(path)


# --- Settings ---

class TestSettings:
    def test_get_missing_returns_none(self, db: Database):
        assert db.get_setting("nonexistent") is None

    def test_set_and_get(self, db: Database):
        db.set_setting("theme", "dark")
        assert db.get_setting("theme") == "dark"

    def test_overwrite(self, db: Database):
        db.set_setting("key", "a")
        db.set_setting("key", "b")
        assert db.get_setting("key") == "b"

    def test_get_all_settings(self, db: Database):
        db.set_setting("a", "1")
        db.set_setting("b", "2")
        result = db.get_all_settings()
        assert result == {"a": "1", "b": "2"}

    def test_delete_setting(self, db: Database):
        db.set_setting("key", "val")
        db.delete_setting("key")
        assert db.get_setting("key") is None


# --- History ---

class TestHistory:
    def _make_record(self, db: Database, **overrides) -> int:
        defaults = {
            "test_type": "echo",
            "test_type_display": "Echocardiogram",
            "summary": "Normal heart function.",
            "full_response": {"explanation": {"overall_summary": "All good."}},
        }
        defaults.update(overrides)
        return db.save_history(**defaults)

    def test_save_and_get(self, db: Database):
        record_id = self._make_record(db)
        record = db.get_history(record_id)
        assert record is not None
        assert record["test_type"] == "echo"
        assert record["full_response"]["explanation"]["overall_summary"] == "All good."

    def test_get_nonexistent(self, db: Database):
        assert db.get_history(9999) is None

    def test_list_newest_first(self, db: Database):
        id1 = self._make_record(db, summary="First")
        id2 = self._make_record(db, summary="Second")
        items, total = db.list_history()
        assert total == 2
        assert len(items) == 2
        # Newest first (id2 inserted after id1)
        assert items[0]["id"] == id2
        assert items[1]["id"] == id1

    def test_pagination(self, db: Database):
        for i in range(5):
            self._make_record(db, summary=f"Record {i}")
        items, total = db.list_history(offset=0, limit=2)
        assert total == 5
        assert len(items) == 2

        items2, total2 = db.list_history(offset=2, limit=2)
        assert total2 == 5
        assert len(items2) == 2

    def test_search_filter(self, db: Database):
        self._make_record(db, summary="Heart is normal")
        self._make_record(db, summary="Lung function test")
        items, total = db.list_history(search="Heart")
        assert total == 1
        assert "Heart" in items[0]["summary"]

    def test_search_by_filename(self, db: Database):
        self._make_record(db, filename="echo_report.pdf", summary="Normal")
        self._make_record(db, filename="blood_test.pdf", summary="Normal")
        items, total = db.list_history(search="echo_report")
        assert total == 1

    def test_hard_delete(self, db: Database):
        record_id = self._make_record(db)
        assert db.delete_history(record_id) is True
        assert db.get_history(record_id) is None

    def test_delete_nonexistent(self, db: Database):
        assert db.delete_history(9999) is False

    def test_save_with_filename(self, db: Database):
        record_id = self._make_record(db, filename="test.pdf")
        record = db.get_history(record_id)
        assert record is not None
        assert record["filename"] == "test.pdf"

    def test_liked_default_is_false(self, db: Database):
        record_id = self._make_record(db)
        record = db.get_history(record_id)
        assert record is not None
        assert record["liked"] == 0

    def test_update_liked_to_true(self, db: Database):
        record_id = self._make_record(db)
        assert db.update_history_liked(record_id, True) is True
        record = db.get_history(record_id)
        assert record is not None
        assert record["liked"] == 1

    def test_update_liked_to_false(self, db: Database):
        record_id = self._make_record(db)
        db.update_history_liked(record_id, True)
        assert db.update_history_liked(record_id, False) is True
        record = db.get_history(record_id)
        assert record is not None
        assert record["liked"] == 0

    def test_update_liked_nonexistent(self, db: Database):
        assert db.update_history_liked(9999, True) is False

    def test_get_liked_examples_empty(self, db: Database):
        assert db.get_liked_examples() == []

    def test_get_liked_examples_returns_liked_only(self, db: Database):
        id1 = self._make_record(db, summary="First")
        id2 = self._make_record(db, summary="Second")
        db.update_history_liked(id1, True)
        examples = db.get_liked_examples()
        assert len(examples) == 1
        # Should return structural metadata, not clinical content
        assert "paragraph_count" in examples[0]
        assert "approx_sentence_count" in examples[0]
        assert "approx_char_length" in examples[0]
        assert "num_key_findings" in examples[0]
        assert "overall_summary" not in examples[0]

    def test_get_liked_examples_respects_limit(self, db: Database):
        for i in range(5):
            rid = self._make_record(db, summary=f"Record {i}")
            db.update_history_liked(rid, True)
        examples = db.get_liked_examples(limit=2)
        assert len(examples) == 2

    def test_get_liked_examples_filters_by_test_type(self, db: Database):
        id1 = self._make_record(db, test_type="echo", summary="Echo rec")
        id2 = self._make_record(db, test_type="cbc", summary="CBC rec")
        db.update_history_liked(id1, True)
        db.update_history_liked(id2, True)
        examples = db.get_liked_examples(test_type="echo")
        assert len(examples) == 1

    def test_list_history_includes_liked_field(self, db: Database):
        self._make_record(db)
        items, total = db.list_history()
        assert "liked" in items[0]

    def test_list_history_liked_only_filter(self, db: Database):
        id1 = self._make_record(db, summary="Not liked")
        id2 = self._make_record(db, summary="Liked one")
        db.update_history_liked(id2, True)
        items, total = db.list_history(liked_only=True)
        assert total == 1
        assert items[0]["id"] == id2


# --- Templates ---

class TestTemplates:
    def test_create_and_get(self, db: Database):
        tpl = db.create_template(name="My Template", tone="warm")
        assert tpl is not None
        assert tpl["name"] == "My Template"
        assert tpl["tone"] == "warm"
        assert tpl["id"] is not None
        assert tpl["created_at"] is not None
        assert tpl["updated_at"] is not None

        fetched = db.get_template(tpl["id"])
        assert fetched is not None
        assert fetched["name"] == "My Template"

    def test_get_nonexistent(self, db: Database):
        assert db.get_template(9999) is None

    def test_create_with_all_fields(self, db: Database):
        tpl = db.create_template(
            name="Full Template",
            test_type="cbc",
            tone="reassuring",
            structure_instructions="Start with overview.",
            closing_text="Please follow up.",
        )
        assert tpl["test_type"] == "cbc"
        assert tpl["tone"] == "reassuring"
        assert tpl["structure_instructions"] == "Start with overview."
        assert tpl["closing_text"] == "Please follow up."

    def test_list_templates(self, db: Database):
        # Account for the built-in "Lipid Panel" template seeded on init
        baseline_items, baseline_total = db.list_templates()
        db.create_template(name="First")
        db.create_template(name="Second")
        items, total = db.list_templates()
        assert total == baseline_total + 2
        assert len(items) == baseline_total + 2
        names = {item["name"] for item in items}
        assert "First" in names
        assert "Second" in names

    def test_list_includes_builtin(self, db: Database):
        items, total = db.list_templates()
        assert total >= 1
        builtin_names = {item["name"] for item in items if item.get("is_builtin")}
        assert "Lipid Panel" in builtin_names

    def test_update_template(self, db: Database):
        tpl = db.create_template(name="Original", tone="formal")
        updated = db.update_template(tpl["id"], name="Renamed", tone="casual")
        assert updated is not None
        assert updated["name"] == "Renamed"
        assert updated["tone"] == "casual"
        assert updated["updated_at"] >= tpl["updated_at"]

    def test_update_partial(self, db: Database):
        tpl = db.create_template(name="Template", tone="warm", test_type="echo")
        updated = db.update_template(tpl["id"], tone="cold")
        assert updated is not None
        assert updated["tone"] == "cold"
        # Other fields unchanged
        assert updated["name"] == "Template"
        assert updated["test_type"] == "echo"

    def test_update_clear_field_to_none(self, db: Database):
        tpl = db.create_template(name="Template", tone="warm", test_type="echo")
        updated = db.update_template(tpl["id"], tone=None)
        assert updated is not None
        assert updated["tone"] is None
        # Other fields unchanged
        assert updated["name"] == "Template"
        assert updated["test_type"] == "echo"

    def test_update_nonexistent(self, db: Database):
        assert db.update_template(9999, name="nope") is None

    def test_delete_template(self, db: Database):
        tpl = db.create_template(name="To Delete")
        assert db.delete_template(tpl["id"]) is True
        assert db.get_template(tpl["id"]) is None

    def test_delete_nonexistent(self, db: Database):
        assert db.delete_template(9999) is False
