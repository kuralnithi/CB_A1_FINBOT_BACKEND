"""Database models for FinBot."""
from datetime import datetime
from sqlalchemy import String, Integer, DateTime, Boolean, Float, Text, JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql import func

class Base(DeclarativeBase):
    pass

class UserDB(Base):
    """PostgreSQL user model mapping."""
    __tablename__ = "users"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    email: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=True)
    hashed_password: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False, default="employee")
    display_name: Mapped[str] = mapped_column(String, nullable=False, default="")
    extra_roles: Mapped[str] = mapped_column(String, nullable=True, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class QueryLog(Base):
    """Audit log of user queries for LangSmith promotion."""
    __tablename__ = "query_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String, index=True, nullable=False)
    query: Mapped[str] = mapped_column(String, nullable=False)
    answer: Mapped[str] = mapped_column(String, nullable=False)
    user_role: Mapped[str] = mapped_column(String, nullable=False)
    routing_selected: Mapped[str] = mapped_column(String, nullable=True)
    is_exported: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class EvalRun(Base):
    """Stores the results of each LangSmith evaluation run."""
    __tablename__ = "eval_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    experiment_name: Mapped[str] = mapped_column(String, nullable=False)
    dataset_name: Mapped[str] = mapped_column(String, nullable=False, default="finbot_eval")
    total_examples: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    avg_exact_match: Mapped[float] = mapped_column(Float, nullable=True)
    results_url: Mapped[str] = mapped_column(String, nullable=True)
    # JSON blob of per-example results: [{query, ground_truth, actual_answer, score}]
    per_example_results: Mapped[str] = mapped_column(Text, nullable=True)
    triggered_by: Mapped[str] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

