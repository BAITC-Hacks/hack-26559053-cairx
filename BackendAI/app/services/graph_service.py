import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import networkx as nx
import numpy as np
import pandas as pd
from app.core.config import settings
from app.schemas.graph import (
    ClusterDetail,
    GraphEdgeDetail,
    GraphNodeDetail,
    GraphStatsResponse,
    TopNodeItem,
)

logger = logging.getLogger("backend_ai.services.graph")

ROLES = ["consolidator", "transit", "distributor", "terminal", "coordinator", "peripheral"]


class GraphService:
    def __init__(self):
        self.edges_df: Optional[pd.DataFrame] = None
        self.nodes_df: Optional[pd.DataFrame] = None
        self.tx_df: Optional[pd.DataFrame] = None
        self.processed_nodes_df: Optional[pd.DataFrame] = None
        self.clusters_df: Optional[pd.DataFrame] = None
        self.G: Optional[nx.DiGraph] = None
        self.is_loaded: bool = False

    def load_data(self, data_path: Optional[Path] = None) -> bool:
        """Loads parquet datasets and computes graph metrics."""
        path = data_path or settings.data_path
        logger.info(f"Loading data from directory: {path}")

        edges_file = path / "edges.parquet"
        nodes_file = path / "nodes.parquet"
        tx_file = path / "transactions.parquet"

        if not (edges_file.exists() and nodes_file.exists()):
            logger.warning(f"Parquet files not found in {path}. Graph service uninitialized.")
            return False

        try:
            self.edges_df = pd.read_parquet(edges_file)
            self.nodes_df = pd.read_parquet(nodes_file)
            if tx_file.exists():
                self.tx_df = pd.read_parquet(tx_file)
                self.tx_df["date"] = pd.to_datetime(self.tx_df["date"])

            self._build_graph()
            self._compute_metrics_and_roles()
            self._compute_clusters()
            self.is_loaded = True
            logger.info("Graph analysis pipeline successfully initialized and cached.")
            return True
        except Exception as e:
            logger.error(f"Error loading graph data: {e}", exc_info=True)
            return False

    def _build_graph(self):
        self.G = nx.DiGraph()
        for r in self.edges_df.itertuples(index=False):
            self.G.add_edge(
                r.src,
                r.dst,
                sum_kzt=float(r.sum_kzt),
                n_tx=int(r.n_tx),
                depth=int(r.depth),
            )

    def _compute_metrics_and_roles(self):
        G = self.G
        nodes = self.nodes_df.copy()

        in_deg = dict(G.in_degree())
        out_deg = dict(G.out_degree())
        in_kzt = dict(G.in_degree(weight="sum_kzt"))
        out_kzt = dict(G.out_degree(weight="sum_kzt"))
        in_tx = dict(G.in_degree(weight="n_tx"))
        out_tx = dict(G.out_degree(weight="n_tx"))

        # Weighted PageRank
        try:
            pr = nx.pagerank(G, weight="sum_kzt", max_iter=200)
        except Exception:
            pr = nx.pagerank(G, weight="sum_kzt", alpha=0.85)

        df = nodes[["gid", "depth", "is_seed"]].copy()
        df["in_deg"] = df.gid.map(in_deg).fillna(0).astype(int)
        df["out_deg"] = df.gid.map(out_deg).fillna(0).astype(int)
        df["in_kzt"] = df.gid.map(in_kzt).fillna(0.0)
        df["out_kzt"] = df.gid.map(out_kzt).fillna(0.0)
        df["in_tx"] = df.gid.map(in_tx).fillna(0).astype(int)
        df["out_tx"] = df.gid.map(out_tx).fillna(0).astype(int)
        df["pagerank"] = df.gid.map(pr).fillna(0.0)

        # Pass-through ratio
        df["pass_through"] = np.where(df.in_kzt > 0, df.out_kzt / df.in_kzt.replace(0, np.nan), np.nan)
        df["truncated_by_depth"] = (df.depth == 4) & (df.out_deg == 0)

        # High-precision role heuristics
        roles: List[str] = []
        role_scores: List[float] = []
        priority_scores: List[float] = []
        evidences: List[str] = []

        max_in_kzt = df.in_kzt.max() or 1.0
        max_out_kzt = df.out_kzt.max() or 1.0
        max_pr = df.pagerank.max() or 1.0

        for row in df.itertuples():
            in_d = row.in_deg
            out_d = row.out_deg
            in_val = row.in_kzt
            out_val = row.out_kzt
            pt = row.pass_through
            depth = row.depth
            is_seed = row.is_seed
            trunc = row.truncated_by_depth
            pr_val = row.pagerank

            # Classification logic
            role = "peripheral"
            score = 0.5
            priority = 0.1
            evidence = f"in_deg={in_d}, out_deg={out_d}, in={in_val:,.0f} KZT"

            if (in_d >= 3) and (out_d <= 2 or (not np.isnan(pt) and pt < 0.6)):
                role = "consolidator"
                score = min(1.0, 0.6 + 0.1 * min(in_d, 5))
                priority = min(1.0, 0.4 + 0.6 * (in_val / max_in_kzt))
                evidence = f"Сбор средств: in_deg={in_d}, in={in_val:,.0f}KZT, out_deg={out_d}"
            elif (out_d >= 5) and (in_d <= 3 or out_d / max(in_d, 1) >= 2.5):
                role = "distributor"
                score = min(1.0, 0.6 + 0.08 * min(out_d, 6))
                priority = min(1.0, 0.4 + 0.6 * (out_val / max_out_kzt))
                evidence = f"Веерная рассылка: out_deg={out_d}, out={out_val:,.0f}KZT, in_deg={in_d}"
            elif (in_d > 0 and out_d > 0) and (not np.isnan(pt) and 0.7 <= pt <= 1.35):
                role = "transit"
                score = min(1.0, 0.7 + 0.3 * (1.0 - abs(pt - 1.0)))
                priority = min(1.0, 0.3 + 0.5 * (out_val / max_out_kzt) + 0.2 * (pr_val / max_pr))
                evidence = f"Транзит без задержки: pass_through={pt:.2f}, in={in_val:,.0f}KZT, out={out_val:,.0f}KZT"
            elif (out_d == 0 and in_d > 0 and depth < 4) or (out_d == 0 and in_d >= 2 and not trunc):
                role = "terminal"
                score = 0.85
                priority = min(1.0, 0.5 + 0.5 * (in_val / max_in_kzt))
                evidence = f"Конечный получатель (сток): in_deg={in_d}, in={in_val:,.0f}KZT, out_deg=0"
            elif (in_d >= 2 and out_d >= 2) and (pr_val > df.pagerank.quantile(0.90) or is_seed):
                role = "coordinator"
                score = min(1.0, 0.65 + 0.35 * (pr_val / max_pr))
                priority = min(1.0, 0.5 + 0.5 * (pr_val / max_pr))
                evidence = f"Координатор хаба: PageRank={pr_val:.5f}, in_deg={in_d}, out_deg={out_d}"
            elif trunc:
                role = "peripheral"
                score = 0.5
                priority = 0.15
                evidence = f"4-е колено без исходящих (граница обхода): in_deg={in_d}, in={in_val:,.0f}KZT"
            else:
                role = "peripheral"
                score = 0.6
                priority = min(1.0, 0.1 + 0.2 * (in_val / max_in_kzt))
                evidence = f"Периферийный узел: in_deg={in_d}, out_deg={out_d}"

            roles.append(role)
            role_scores.append(round(float(score), 3))
            priority_scores.append(round(float(priority), 3))
            evidences.append(evidence[:200])

        df["role"] = roles
        df["role_score"] = role_scores
        df["priority_score"] = priority_scores
        df["evidence"] = evidences
        df["cluster_id"] = -1

        self.processed_nodes_df = df

    def _compute_clusters(self):
        """Runs Louvain community detection on undirected projection."""
        UG = self.G.to_undirected()
        try:
            communities = list(nx.community.louvain_communities(UG, weight="sum_kzt", seed=42))
        except Exception:
            communities = [set(c) for c in nx.connected_components(UG)]

        node_to_cluster = {}
        for c_id, comm in enumerate(communities):
            for gid in comm:
                node_to_cluster[gid] = c_id

        self.processed_nodes_df["cluster_id"] = self.processed_nodes_df.gid.map(node_to_cluster).fillna(-1).astype(int)

        # Build cluster summaries
        cluster_records = []
        for c_id, comm in enumerate(communities):
            comm_nodes = self.processed_nodes_df[self.processed_nodes_df.gid.isin(comm)]
            n_nodes = len(comm_nodes)
            n_seed = int(comm_nodes.is_seed.sum())
            sub_g = self.G.subgraph(comm)
            sum_kzt_internal = float(sum(d.get("sum_kzt", 0.0) for _, _, d in sub_g.edges(data=True)))
            top_gids = ",".join(map(str, comm_nodes.nlargest(3, "priority_score").gid.tolist()))

            # Hypothesis generator
            if n_seed > 3:
                hypo = f"Крупный межсетевой синдикат ({n_seed} seeds): оборот {sum_kzt_internal:,.0f} KZT."
            elif sum_kzt_internal > 10_000_000:
                hypo = f"Высокооборотный кластер переводов: топ-акторы [{top_gids}]."
            else:
                hypo = f"Локальная транзакционная группа из {n_nodes} узлов."

            cluster_records.append({
                "cluster_id": c_id,
                "n_nodes": n_nodes,
                "n_seed": n_seed,
                "sum_kzt_internal": sum_kzt_internal,
                "top_gids": top_gids,
                "hypothesis": hypo,
            })

        self.clusters_df = pd.DataFrame(cluster_records).sort_values("sum_kzt_internal", ascending=False)

    def get_stats(self) -> GraphStatsResponse:
        if not self.is_loaded:
            return GraphStatsResponse(
                total_nodes=0,
                total_edges=0,
                total_transactions=0,
                seed_nodes=0,
                total_volume_kzt=0.0,
            )

        role_counts = self.processed_nodes_df["role"].value_counts().to_dict()
        date_range = None
        if self.tx_df is not None:
            date_range = f"{self.tx_df.date.min().date()} - {self.tx_df.date.max().date()}"

        return GraphStatsResponse(
            total_nodes=len(self.processed_nodes_df),
            total_edges=len(self.edges_df),
            total_transactions=len(self.tx_df) if self.tx_df is not None else 0,
            seed_nodes=int(self.processed_nodes_df.is_seed.sum()),
            total_volume_kzt=float(self.edges_df.sum_kzt.sum()),
            date_range=date_range,
            roles_distribution=role_counts,
            clusters_count=len(self.clusters_df) if self.clusters_df is not None else 0,
        )

    def get_nodes(
        self,
        page: int = 1,
        page_size: int = 50,
        role: Optional[str] = None,
        search_gid: Optional[int] = None,
        cluster_id: Optional[int] = None,
    ) -> Tuple[List[GraphNodeDetail], int]:
        if not self.is_loaded:
            return [], 0

        df = self.processed_nodes_df
        if role:
            df = df[df.role == role]
        if search_gid is not None:
            df = df[df.gid == search_gid]
        if cluster_id is not None:
            df = df[df.cluster_id == cluster_id]

        total = len(df)
        start = (page - 1) * page_size
        end = start + page_size
        items_df = df.iloc[start:end]

        results = []
        for r in items_df.itertuples(index=False):
            pt = None if np.isnan(r.pass_through) else float(r.pass_through)
            results.append(
                GraphNodeDetail(
                    gid=int(r.gid),
                    depth=int(r.depth),
                    is_seed=bool(r.is_seed),
                    in_deg=int(r.in_deg),
                    out_deg=int(r.out_deg),
                    in_kzt=float(r.in_kzt),
                    out_kzt=float(r.out_kzt),
                    in_tx=int(r.in_tx),
                    out_tx=int(r.out_tx),
                    pagerank=float(r.pagerank),
                    pass_through=pt,
                    truncated_by_depth=bool(r.truncated_by_depth),
                    role=str(r.role),
                    role_score=float(r.role_score),
                    cluster_id=int(r.cluster_id),
                    priority_score=float(r.priority_score),
                    evidence=str(r.evidence),
                )
            )
        return results, total

    def get_node_by_gid(self, gid: int) -> Optional[GraphNodeDetail]:
        if not self.is_loaded:
            return None
        match = self.processed_nodes_df[self.processed_nodes_df.gid == gid]
        if match.empty:
            return None
        r = match.iloc[0]
        pt = None if np.isnan(r["pass_through"]) else float(r["pass_through"])
        return GraphNodeDetail(
            gid=int(r["gid"]),
            depth=int(r["depth"]),
            is_seed=bool(r["is_seed"]),
            in_deg=int(r["in_deg"]),
            out_deg=int(r["out_deg"]),
            in_kzt=float(r["in_kzt"]),
            out_kzt=float(r["out_kzt"]),
            in_tx=int(r["in_tx"]),
            out_tx=int(r["out_tx"]),
            pagerank=float(r["pagerank"]),
            pass_through=pt,
            truncated_by_depth=bool(r["truncated_by_depth"]),
            role=str(r["role"]),
            role_score=float(r["role_score"]),
            cluster_id=int(r["cluster_id"]),
            priority_score=float(r["priority_score"]),
            evidence=str(r["evidence"]),
        )

    def get_top_nodes(self, limit: int = 25) -> List[TopNodeItem]:
        if not self.is_loaded:
            return []
        top_df = self.processed_nodes_df.sort_values("priority_score", ascending=False).head(limit)
        items = []
        for rank, (_, row) in enumerate(top_df.iterrows(), start=1):
            items.append(
                TopNodeItem(
                    rank=rank,
                    gid=int(row["gid"]),
                    role=str(row["role"]),
                    priority_score=float(row["priority_score"]),
                    why=str(row["evidence"]),
                )
            )
        return items

    def get_clusters(self, limit: int = 50) -> List[ClusterDetail]:
        if self.clusters_df is None:
            return []
        items = []
        for _, r in self.clusters_df.head(limit).iterrows():
            items.append(
                ClusterDetail(
                    cluster_id=int(r["cluster_id"]),
                    n_nodes=int(r["n_nodes"]),
                    n_seed=int(r["n_seed"]),
                    sum_kzt_internal=float(r["sum_kzt_internal"]),
                    top_gids=str(r["top_gids"]),
                    hypothesis=str(r["hypothesis"]),
                )
            )
        return items

    def get_subgraph(self, center_gid: int, hops: int = 1, max_nodes: int = 50) -> Tuple[List[GraphNodeDetail], List[GraphEdgeDetail]]:
        if not self.is_loaded or self.G is None or center_gid not in self.G:
            return [], []

        # Find ego network
        sub_nodes = {center_gid}
        current_layer = {center_gid}
        for _ in range(hops):
            next_layer = set()
            for node in current_layer:
                next_layer.update(self.G.successors(node))
                next_layer.update(self.G.predecessors(node))
            sub_nodes.update(next_layer)
            current_layer = next_layer
            if len(sub_nodes) >= max_nodes:
                break

        sub_nodes = list(sub_nodes)[:max_nodes]
        subgraph = self.G.subgraph(sub_nodes)

        nodes_list, _ = self.get_nodes(page=1, page_size=len(sub_nodes))
        filtered_nodes = [n for n in nodes_list if n.gid in sub_nodes]

        edges_list = []
        for u, v, data in subgraph.edges(data=True):
            edges_list.append(
                GraphEdgeDetail(
                    src=u,
                    dst=v,
                    sum_kzt=float(data.get("sum_kzt", 0.0)),
                    n_tx=int(data.get("n_tx", 1)),
                    depth=int(data.get("depth", 1)),
                )
            )

        return filtered_nodes, edges_list


graph_service = GraphService()
