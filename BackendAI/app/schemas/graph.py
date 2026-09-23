from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class GraphNodeDetail(BaseModel):
    gid: int
    depth: int
    is_seed: bool
    in_deg: int
    out_deg: int
    in_kzt: float
    out_kzt: float
    in_tx: int
    out_tx: int
    pagerank: float
    pass_through: Optional[float] = None
    truncated_by_depth: bool = False
    role: str = ""
    role_score: float = 0.0
    cluster_id: int = -1
    priority_score: float = 0.0
    evidence: str = ""


class GraphEdgeDetail(BaseModel):
    src: int
    dst: int
    sum_kzt: float
    n_tx: int
    depth: int


class ClusterDetail(BaseModel):
    cluster_id: int
    n_nodes: int
    n_seed: int
    sum_kzt_internal: float
    top_gids: str
    hypothesis: str


class TopNodeItem(BaseModel):
    rank: int
    gid: int
    role: str
    priority_score: float
    why: str


class GraphStatsResponse(BaseModel):
    total_nodes: int
    total_edges: int
    total_transactions: int
    seed_nodes: int
    total_volume_kzt: float
    date_range: Optional[str] = None
    roles_distribution: Dict[str, int] = Field(default_factory=dict)
    clusters_count: int = 0


class SubgraphRequest(BaseModel):
    gid: int
    hops: int = Field(default=1, ge=1, le=3)
    max_nodes: int = Field(default=50, ge=5, le=200)


class SubgraphResponse(BaseModel):
    center_gid: int
    nodes: List[GraphNodeDetail]
    edges: List[GraphEdgeDetail]
