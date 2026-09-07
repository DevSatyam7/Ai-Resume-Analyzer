from sqlalchemy import Column, Integer, String, Text, ForeignKey
from db import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True)
    password = Column(String(255))

class Report(Base):
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    resume_text = Column(Text)
    result = Column(Text)
    from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime

class SyllabusCache(Base):
    __tablename__ = "syllabus_cache"

    id = Column(Integer, primary_key=True, index=True)
    normalized_query = Column(String(255), unique=True, index=True, nullable=False)
    display_title = Column(String(255), nullable=False)
    content_json = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
