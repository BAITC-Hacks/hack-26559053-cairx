import math
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query, status
from app.core.config import settings
from app.schemas.common import APIResponse, PaginatedResponse
from app.schemas.graph import (
    ClusterDetail,
    GraphNodeDetail,
    GraphStatsResponse,
    SubgraphRequest,
    SubgraphResponse,
    TopNodeItem,
)
from app.services.graph_service import graph_service

router = APIRouter()


@router.get("/stats", response_model=APIResponse[GraphStatsResponse], summary="Get overall graph dataset statistics")
async def get_stats():
    if not graph_service.is_loaded:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Graph dataset is not currently loaded.",
        )
    return APIResponse(data=graph_service.get_stats(), message="Graph statistics retrieved")


@router.get("/nodes", response_model=APIResponse[PaginatedResponse[GraphNodeDetail]], summary="List nodes with pagination and filters")
async def list_nodes(
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=50, ge=1, le=500, description="Items per page"),
    role: Optional[str] = Query(default=None, description="Filter by role"),
    search_gid: Optional[int] = Query(default=None, description="Filter by exact GID"),
    cluster_id: Optional[int] = Query(default=None, description="Filter by Cluster ID"),
):
    if not graph_service.is_loaded:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Graph dataset is not currently loaded.",
        )

    nodes, total = graph_service.get_nodes(
        page=page,
        page_size=page_size,
        role=role,
        search_gid=search_gid,
        cluster_id=cluster_id,
    )

    total_pages = math.ceil(total / page_size) if total > 0 else 0
    paginated = PaginatedResponse(
        items=nodes,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )
    return APIResponse(data=paginated, message=f"Retrieved {len(nodes)} nodes")


@router.get("/nodes/{gid}", response_model=APIResponse[GraphNodeDetail], summary="Get node detail by GID")
async def get_node_by_gid(gid: int):
    if not graph_service.is_loaded:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Graph dataset is not loaded.",
        )

    node = graph_service.get_node_by_gid(gid)
    if not node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Node with GID {gid} not found.",
        )
    return APIResponse(data=node, message=f"Node {gid} retrieved")


@router.get("/top-nodes", response_model=APIResponse[List[TopNodeItem]], summary="Get top priority nodes for AML investigation")
async def get_top_nodes(limit: int = Query(default=25, ge=1, le=100)):
    if not graph_service.is_loaded:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Graph dataset is not loaded.",
        )

    items = graph_service.get_top_nodes(limit=limit)
    return APIResponse(data=items, message=f"Retrieved top {len(items)} nodes")


@router.get("/clusters", response_model=APIResponse[List[ClusterDetail]], summary="Get detected communities/clusters and hypotheses")
async def get_clusters(limit: int = Query(default=50, ge=1, le=100)):
    if not graph_service.is_loaded:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Graph dataset is not loaded.",
        )

    clusters = graph_service.get_clusters(limit=limit)
    return APIResponse(data=clusters, message=f"Retrieved {len(clusters)} clusters")


@router.post("/subgraph", response_model=APIResponse[SubgraphResponse], summary="Extract ego-network subgraph for visualization")
async def extract_subgraph(request: SubgraphRequest):
    if not graph_service.is_loaded:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Graph dataset is not loaded.",
        )

    nodes, edges = graph_service.get_subgraph(
        center_gid=request.gid,
        hops=request.hops,
        max_nodes=request.max_nodes,
    )

    data = SubgraphResponse(center_gid=request.gid, nodes=nodes, edges=edges)
    return APIResponse(data=data, message=f"Extracted subgraph for GID {request.gid}")


@router.post("/export", summary="Export nodes_roles.csv, clusters.csv, and top_nodes.csv according to competition rules")
async def export_competition_files(out_dir: str = Query(default="./out")):
    if not graph_service.is_loaded:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Graph dataset is not loaded.",
        )

    out_path = Path(out_dir).resolve()
    out_path.mkdir(parents=True, exist_ok=True)

    # 1. nodes_roles.csv
    nodes_df = graph_service.processed_nodes_df.copy()
    columns_order = [
        "gid", "role", "role_score", "cluster_id", "priority_score", "evidence",
        "in_deg", "out_deg", "in_kzt", "out_kzt", "pagerank", "pass_through",
        "depth", "is_seed", "truncated_by_depth"
    ]
    # Ensure all required columns exist
    for col in columns_order:
        if col not in nodes_df.columns:
            nodes_df[col] = None

    nodes_roles_path = out_path / "nodes_roles.csv"
    nodes_df[columns_order].to_csv(nodes_roles_path, index=False)

    # 2. clusters.csv
    clusters_path = out_path / "clusters.csv"
    if graph_service.clusters_df is not None:
        graph_service.clusters_df.to_csv(clusters_path, index=False)

    # 3. top_nodes.csv
    top_nodes_path = out_path / "top_nodes.csv"
    top_items = graph_service.get_top_nodes(limit=50)
    import pandas as pd
    pd.DataFrame([t.model_dump() for t in top_items]).to_csv(top_nodes_path, index=False)

    return APIResponse(
        data={
            "output_directory": str(out_path),
            "files": ["nodes_roles.csv", "clusters.csv", "top_nodes.csv"],
            "nodes_count": len(nodes_df),
        },
        message="Competition files successfully exported",
    )
