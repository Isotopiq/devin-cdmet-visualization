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
    name: Optional[str] = None
    avatar_url: Optional[str] = None
    is_active: bool
    is_admin: bool
    created_at: dt.datetime


class UserUpdate(BaseModel):
    email: Optional[str] = None
    name: Optional[str] = None
    password: Optional[str] = None


class UserAdminCreate(BaseModel):
    email: str
    name: Optional[str] = None
    password: str
    is_admin: bool = False
    is_active: bool = True


class UserAdminUpdate(BaseModel):
    email: Optional[str] = None
    name: Optional[str] = None
    is_admin: Optional[bool] = None
    is_active: Optional[bool] = None


class AdminLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_id: Optional[int]
    user_email: Optional[str] = None
    action: str
    target_user_id: Optional[int]
    target_user_email: Optional[str] = None
    details: Dict[str, Any]
    created_at: dt.datetime


class SiteSettingsOut(BaseModel):
    login_logo_url: Optional[str]
    dashboard_logo_url: Optional[str]
    favicon_url: Optional[str]
    smtp_host: Optional[str]
    smtp_port: Optional[int]
    smtp_user: Optional[str]
    smtp_from: Optional[str]
    smtp_use_tls: bool = True
    smtp_configured: bool = False


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
    batch_labels: Optional[Dict[str, str]] = None
    enable_isobaric_substitution_check: bool = True
    isobaric_substitution_mode: str = "flag_ambiguous"
    isobaric_substitution_rules: List[Dict[str, Any]] = [{
        "name": "O-/P- ether/vinyl-ether",
        "applicable_classes": ["PC", "PE", "PI", "PS", "PA", "PG", "DG", "TG"],
        "prefix_pair": ["O-", "P-"],
        "db_offset": 1,
        "carbon_count_match": True,
    }]
    isobaric_clustering_enabled: bool = True
    isobaric_mz_tolerance: float = 0.005
    isobaric_rt_tolerance: float = 0.2
    isobaric_rollup_preference: str = "alphabetical"


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
    style: Dict[str, Any] = {}


class ReportRequest(BaseModel):
    include: List[str] = ["pca", "pls_da", "opls_da", "biomarker", "permanova", "volcano", "heatmap", "per_lipid_bars", "lipid_classes", "chain_space"]
    style: Dict[str, Any] = {}
    parameters: Dict[str, Any] = {}


class IsotopeRequest(BaseModel):
    tracer: str
    max_label: int
    natural_abundance_correction: bool = False
    circulating_enrichment: Optional[float] = None
    normalization: str = "none"
    # flux map options
    layout: Optional[str] = "spring"  # spring, curated, circular, kamada_kawai, escher
    graph_mode: Optional[str] = "full"  # full, spanning_tree, k_shortest_paths, bipartite
    edge_weight: Optional[str] = "label_gradient"  # label_gradient, intensity, flux, uniform
    k: Optional[int] = 3
    source_node: Optional[str] = None
    target_node: Optional[str] = None
    map_source: Optional[str] = None  # bigg, gem
    map_id: Optional[str] = None
    map_organism: Optional[str] = None
    selected_groups: Optional[List[str]] = None  # compute per-group flux maps; None = all groups / overall
    style: Optional[str] = "classic"  # classic, dark_modern, minimal, subway
    show_labels: bool = False  # show metabolite/enzyme labels on Escher/flux maps


class PathwayRequest(BaseModel):
    value_type: Optional[str] = "abundance"
    pathway_source: str = "kegg"
    custom_nodes: Optional[List[Dict[str, Any]]] = None
    custom_edges: Optional[List[Dict[str, Any]]] = None
    organism: Optional[str] = "hsa"
    group_a: Optional[str] = None
    group_b: Optional[str] = None
    fc_threshold: Optional[float] = 1.0
    p_threshold: Optional[float] = 0.05
    test: Optional[str] = "t_test"
    multiple_testing: Optional[str] = "fdr_bh"
    features: Optional[List[str]] = None
    top_n: Optional[int] = 20


class SiteSettingsUpdate(BaseModel):
    login_logo_url: Optional[str] = None
    dashboard_logo_url: Optional[str] = None
    favicon_url: Optional[str] = None
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = None
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_from: Optional[str] = None
    smtp_use_tls: Optional[bool] = True


class SMTPSettingsOut(BaseModel):
    host: Optional[str]
    port: Optional[int]
    user: Optional[str]
    from_address: Optional[str]
    use_tls: bool = True
    configured: bool = False


class SampleGroupsUpdate(BaseModel):
    sample_metadata: Dict[str, str]


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str
