from sqlalchemy import Column, Integer, String, Text, Float, ForeignKey, DateTime, Enum, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
import datetime

Base = declarative_base()

class UserRole(enum.Enum):
    user = "user"
    admin = "admin"

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    role = Column(Enum(UserRole), default=UserRole.user, nullable=False)

    # Relationships
    submissions = relationship("Submission", back_populates="user", cascade="all, delete-orphan")

class Problem(Base):
    __tablename__ = "problems"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    problem_description = Column(Text, nullable=False)
    topic = Column(String, nullable=True)
    rubric = Column(Text, nullable=False)
    editorial = Column(Text, nullable=True)
    
    # Relationships
    example_submissions = relationship("ExampleSubmission", back_populates="problem", cascade="all, delete-orphan")
    example_feedbacks = relationship("ExampleFeedback", back_populates="problem", cascade="all, delete-orphan")
    algorithm_guidance = relationship("AlgorithmGuidance", back_populates="problem", uselist=False, cascade="all, delete-orphan")
    
class ExampleSubmission(Base):
    __tablename__ = "example_submissions"

    id = Column(Integer, primary_key=True, index=True)
    problem_id = Column(Integer, ForeignKey("problems.id", ondelete="CASCADE"), nullable=False)
    tag = Column(String, nullable=False)  # correct, tle, wrong, etc.
    code = Column(Text, nullable=False)
    language = Column(String, nullable=False)
    
    # Relationships
    problem = relationship("Problem", back_populates="example_submissions")

class ExampleFeedback(Base):
    __tablename__ = "example_feedbacks"

    id = Column(Integer, primary_key=True, index=True)
    problem_id = Column(Integer, ForeignKey("problems.id", ondelete="CASCADE"), nullable=False)
    tag = Column(String, nullable=False)  # correct, tle, wrong, etc.
    feedback_text = Column(Text, nullable=False)
    
    # Relationships
    problem = relationship("Problem", back_populates="example_feedbacks")

class EvaluationStatus(enum.Enum):
    pending = "pending"
    completed = "completed"
    error = "error"

class Submission(Base):
    __tablename__ = "submissions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    problem_id = Column(Integer, ForeignKey("problems.id", ondelete="CASCADE"), nullable=False)
    code = Column(Text, nullable=False)
    language = Column(String, nullable=False)
    total_score = Column(Float, nullable=True)  # by LLM
    marks_reported = Column(Float, nullable=True)  # by user
    submission_time = Column(DateTime, default=func.now(), nullable=False)
    evaluation_status = Column(Enum(EvaluationStatus), default=EvaluationStatus.pending, nullable=False)
    
    # Relationships
    user = relationship("User", back_populates="submissions")
    problem = relationship("Problem")  # No back_populates - one-way relationship
    evaluation_details = relationship("EvaluationDetail", back_populates="submission", cascade="all, delete-orphan")

class EvaluationDetail(Base):
    __tablename__ = "evaluation_details"

    id = Column(Integer, primary_key=True, index=True)
    submission_id = Column(Integer, ForeignKey("submissions.id", ondelete="CASCADE"), nullable=False)
    criterion_index = Column(Integer, nullable=False)  # Step number in the rubric
    max_score = Column(Float, nullable=False)
    score_obtained = Column(Float, nullable=False)
    feedback = Column(Text, nullable=True)
    
    # Relationships
    submission = relationship("Submission", back_populates="evaluation_details")

class AlgorithmGuidance(Base):
    __tablename__ = "algorithm_guidance"

    id = Column(Integer, primary_key=True, index=True)
    problem_id = Column(Integer, ForeignKey("problems.id", ondelete="CASCADE"), nullable=False, unique=True)
    algorithm_guidance = Column(Text, nullable=False)
    test_cases = Column(Text, nullable=True)
    common_errors = Column(Text, nullable=True)
    key_implementation_patterns = Column(Text, nullable=True)
    misleading_patterns = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    
    # Relationships
    problem = relationship("Problem", back_populates="algorithm_guidance")