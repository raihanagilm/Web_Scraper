"""Model MergeHistory — audit aksi review duplikat (keep/merge/delete_all).

Field JSON sengaja denormalisasi sebagai snapshot sebelum merge.
"""
from datetime import datetime

from sqlalchemy import JSON, Column, DateTime, Enum, Integer, String

from backend.models.base import Base


class MergeHistory(Base):
    __tablename__ = "merge_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    group_key = Column(String(255), nullable=False)
    action = Column(Enum("keep", "merge", "delete_all", name="merge_action_enum"), nullable=False)
    winner_id = Column(Integer, nullable=True)
    member_ids = Column(JSON, nullable=False, default=list)
    field_choices = Column(JSON, nullable=True)
    snapshot_deleted = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)