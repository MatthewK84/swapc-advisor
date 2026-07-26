"""Command-line interface for the SWaP-C down-selection advisor.

The four required inputs are unchanged: mission thread, cost per unit
threshold, flight time and distance requirement, and AOR. Two optional
flags control how aggressively the engine favors attritable systems.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Final

from .knowledge_base import KnowledgeBase, load_knowledge_base
from .models import AdvisorError, Query, Recommendation
from .recommender import recommend
from .report_pdf import write_pdf
from .report_xlsx import write_xlsx

EXIT_OK: Final[int] = 0
EXIT_ERROR: Final[int] = 1

logger: logging.Logger = logging.getLogger("swapc_advisor")


def default_data_dir() -> Path:
    """Knowledge base directory shipped inside the installed package."""
    return Path(__file__).resolve().parent / "data"


def build_parser(kb: KnowledgeBase) -> argparse.ArgumentParser:
    """Argument parser with choices populated from the knowledge base."""
    parser = argparse.ArgumentParser(
        prog="swapc-advisor",
        description="SWaP-C UAS and C-sUAS technology down-selection advisor.",
    )
    parser.add_argument(
        "--mission-thread",
        required=True,
        choices=[t.thread_id for t in kb.mission_threads],
        help="Mission thread id.",
    )
    parser.add_argument(
        "--cost-threshold",
        required=True,
        type=float,
        help="Maximum acceptable cost per unit in USD.",
    )
    parser.add_argument(
        "--flight-time",
        required=True,
        type=float,
        help="Required flight time in minutes (0 for ground-based only needs).",
    )
    parser.add_argument(
        "--distance",
        required=True,
        type=float,
        help="Required flight distance or engagement range in km.",
    )
    parser.add_argument(
        "--aor",
        required=True,
        choices=[a.aor_id for a in kb.aors],
        help="Combatant command AOR.",
    )
    parser.add_argument(
        "--posture",
        default="attritable_first",
        choices=[p.posture_id for p in kb.taxonomy.postures],
        help="Scoring posture. Default favors attritable low-SWaP-C systems.",
    )
    parser.add_argument(
        "--max-cost-tier",
        default="T4",
        choices=[t.tier for t in kb.taxonomy.cost_tiers],
        help="Hard ceiling on cost tier. Set T1 to exclude anything above attritable.",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=default_data_dir(),
        help="Override the knowledge base directory.",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path(),
        help="Directory for the PDF and xlsx outputs.",
    )
    return parser


def run_query(kb: KnowledgeBase, query: Query, out_dir: Path) -> tuple[Path, Path]:
    """Execute one query and write both report files."""
    rec: Recommendation = recommend(kb, query)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp: str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    stem: str = f"swapc_{query.aor_id}_{query.mission_thread_id}_{stamp}"
    pdf_path: Path = write_pdf(rec, out_dir / f"{stem}.pdf", kb.disclaimer)
    xlsx_path: Path = write_xlsx(rec, out_dir / f"{stem}.xlsx", kb.disclaimer)
    logger.info("%s", rec.summary)
    logger.info("Tier distribution: %s", rec.tier_distribution)
    logger.info("Wrote %s and %s", pdf_path, xlsx_path)
    return pdf_path, xlsx_path


def _early_data_dir(args: list[str]) -> Path:
    """Read --data-dir before the full parser is built, since the parser's
    choices are populated from the knowledge base itself."""
    if "--data-dir" not in args:
        return default_data_dir()
    index: int = args.index("--data-dir")
    if index + 1 >= len(args):
        return default_data_dir()
    return Path(args[index + 1])


def main(argv: list[str] | None = None) -> int:
    """CLI entry point returning a process exit code."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    data_dir: Path = _early_data_dir(argv if argv is not None else sys.argv[1:])
    try:
        kb: KnowledgeBase = load_knowledge_base(data_dir)
    except AdvisorError:
        logger.exception("Knowledge base load failed")
        return EXIT_ERROR
    parser: argparse.ArgumentParser = build_parser(kb)
    args: argparse.Namespace = parser.parse_args(argv)
    query: Query = Query(
        mission_thread_id=args.mission_thread,
        cost_threshold_usd=args.cost_threshold,
        flight_time_min=args.flight_time,
        distance_km=args.distance,
        aor_id=args.aor,
        posture_id=args.posture,
        max_cost_tier=args.max_cost_tier,
    )
    try:
        run_query(kb, query, args.out_dir)
    except AdvisorError:
        logger.exception("Down-selection failed")
        return EXIT_ERROR
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
