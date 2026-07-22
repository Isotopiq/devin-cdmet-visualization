from typing import Optional, Dict, Any, List
from pydantic import BaseModel, ConfigDict
import datetime as dt


class UserBase(BaseModel):
    email: str


class UserCreate(UserBase):
    password: str


class UserOut(UserBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    is_active: bool
    created_at: dt.datetime


class Token(BaseModel):
    access_token: str
    token_type: str


class ProjectBase(BaseModel):
    name: str
    description: Optional[str] = None


class ProjectCreate(ProjectBase):
    pass


class ProjectOut(ProjectBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    owner_id: int
    created_at: dt.datetime
    updated_at: dt.datetime


class UploadedFileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    project_id: int
    original_name: str
    stored_name: str
    file_type: Optional[str]
    detected_format: Optional[str]
    sheets: List[str]
    selected_sheet: Optional[str]
    status: str
    created_at: dt.datetime


class DatasetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    project_id: int
    source_file_id: Optional[int]
    name: str
    feature_type: str
    sample_metadata: Dict[str, Any]
    feature_metadata: List[Dict[str, Any]]
    created_at: dt.datetime


class AnalysisOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    project_id: int
    dataset_id: int
    name: str
    analysis_type: str
    created_at: dt.datetime


class ColumnMapping(BaseModel):
    feature_id: Optional[str] = None
    name: Optional[str] = None
    formula: Optional[str] = None
    mz: Optional[str] = None
    rt: Optional[str] = None
    adduct: Optional[str] = None
    lipid_class: Optional[str] = None
    grade: Optional[str] = None
    sample_columns: List[str] = []
    sample_groups: Dict[str, str] = {}


class ImportPreview(BaseModel):
    detected_format: Optional[str]
    sheets: List[str]
    columns: List[str]
    sample_columns: List[str]
    feature_columns: List[str]
    row_count: int
    suggested_mapping: Dict[str, Any]
    sample_groups: Dict[str, str]


class PreprocessingParams(BaseModel):
    missing_value_filter: float = 0.0
    blank_subtraction: bool = False
    blank_columns: List[str] = []
    qc_cv_filter: float = 0.0
    qc_columns: List[str] = []
    duplicate_handling: str = "mean"
    imputation: str = "none"
    log_transform: bool = False
    scale: str = "none"
    normalization: str = "none"
    custom_factor: Optional[float] = None
    batch_correction: str = "none"
    batch_column: Optional[str] = None


class StatsRequest(BaseModel):
    test: str
    group_a: Optional[str] = None
    group_b: Optional[str] = None
    value_column: Optional[str] = None
    group_column: Optional[str] = None
    paired: bool = False
    multiple_testing: str = "fdr_bh"
    alpha: float = 0.05


class PlotRequest(BaseModel):
    plot_type: str
    parameters: Dict[str, Any] = {}


class IsotopeRequest(BaseModel):
    tracer: str
    max_label: int
    natural_abundance_correction: bool = False
    circulating_enrichment: Optional[float] = None
    normalization: str = "none"


class PathwayRequest(BaseModel):
    value_type: str
    pathway_source: str = "kegg"
    custom_nodes: Optional[List[Dict[str, Any]]] = None
    custom_edges: Optional[List[Dict[str, Any]]] = None
