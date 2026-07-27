import datetime as dt
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text, JSON
from sqlalchemy.orm import relationship
from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=dt.datetime.utcnow)

    projects = relationship("Project", back_populates="owner", cascade="all, delete-orphan")


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), default=dt.datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow)

    owner = relationship("User", back_populates="projects")
    files = relationship("UploadedFile", back_populates="project", cascade="all, delete-orphan")
    datasets = relationship("Dataset", back_populates="project", cascade="all, delete-orphan")
    analyses = relationship("Analysis", back_populates="project", cascade="all, delete-orphan")


class UploadedFile(Base):
    __tablename__ = "uploaded_files"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    original_name = Column(String, nullable=False)
    stored_name = Column(String, nullable=False)
    file_type = Column(String, nullable=True)
    detected_format = Column(String, nullable=True)
    sheets = Column(JSON, default=list)
    selected_sheet = Column(String, nullable=True)
    column_mapping = Column(JSON, default=dict)
    sample_groups = Column(JSON, default=dict)
    file_metadata = Column(JSON, default=dict)
    status = Column(String, default="uploaded")
    created_at = Column(DateTime(timezone=True), default=dt.datetime.utcnow)

    project = relationship("Project", back_populates="files")
    dataset = relationship("Dataset", back_populates="source_file")


class Dataset(Base):
    __tablename__ = "datasets"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    source_file_id = Column(Integer, ForeignKey("uploaded_files.id"), nullable=True)
    name = Column(String, nullable=False)
    feature_type = Column(String, nullable=False, default="metabolite")
    data_matrix = Column(JSON, default=dict)
    sample_metadata = Column(JSON, default=dict)
    feature_metadata = Column(JSON, default=dict)
    processing_history = Column(JSON, default=list)
    created_at = Column(DateTime(timezone=True), default=dt.datetime.utcnow)

    project = relationship("Project", back_populates="datasets")
    source_file = relationship("UploadedFile", back_populates="dataset")
    analyses = relationship("Analysis", back_populates="dataset", cascade="all, delete-orphan")


class Analysis(Base):
    __tablename__ = "analyses"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    dataset_id = Column(Integer, ForeignKey("datasets.id"), nullable=False)
    name = Column(String, nullable=False)
    analysis_type = Column(String, nullable=False)
    parameters = Column(JSON, default=dict)
    results = Column(JSON, default=dict)
    plots = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), default=dt.datetime.utcnow)

    project = relationship("Project", back_populates="analyses")
    dataset = relationship("Dataset", back_populates="analyses")
