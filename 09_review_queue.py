"""
STEP 9: HUMAN REVIEW QUEUE (NEW in v2)

Ported from Hamilton MVP's HITL review queue system.
Simplified to work with CSV checkpoints (no database).

Provides a CLI for manual review of borderline leads that scored
between the qualification threshold and a clear reject.

Usage:
    python 09_review_queue.py              # List leads needing review
    python 09_review_queue.py --approve 5  # Approve lead at rank 5
    python 09_review_queue.py --reject 12  # Reject lead at rank 12
    python 09_review_queue.py --stats      # Show review statistics
"""

import pandas as pd
import sys
import os
import argparse
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))
from config import CHECKPOINT_SCORED, QUALIFICATION_THRESHOLD


REVIEW_LOG_PATH = "data/review_log.csv"


def load_scored():
    """Load the scored candidates file."""
    if not os.path.exists(CHECKPOINT_SCORED):
        print(f"  [ERROR] Scored file not found: {CHECKPOINT_SCORED}")
        print(f"  [ERROR] Run the pipeline first (steps 00-06).")
        sys.exit(1)
    return pd.read_csv(CHECKPOINT_SCORED)


def load_review_log():
    """Load the review log (creates if doesn't exist)."""
    if os.path.exists(REVIEW_LOG_PATH):
        return pd.read_csv(REVIEW_LOG_PATH)
    return pd.DataFrame(columns=["rank", "company_name", "action", "reason", "reviewed_at"])


def save_review_log(log_df):
    """Save the review log."""
    os.makedirs(os.path.dirname(REVIEW_LOG_PATH), exist_ok=True)
    log_df.to_csv(REVIEW_LOG_PATH, index=False, encoding="utf-8")


def list_review_needed(df):
    """List leads that need human review."""
    # Review queue: scored but below qualification threshold
    review_df = df[df["qualification"] == "REVIEW_REQUIRED"].copy()

    if len(review_df) == 0:
        print("\n  All leads are either QUALIFIED or below threshold. No review needed.")
        return

    # Check which have already been reviewed
    log = load_review_log()
    reviewed_ranks = set(log["rank"].tolist()) if len(log) > 0 else set()

    print(f"\n  Leads Needing Review ({len(review_df)} total, {len(reviewed_ranks)} already reviewed)\n")
    print(f"  {'Rank':<6} {'Company':<40} {'Score':<8} {'Rev Conf':<10} {'Reviewed'}")
    print(f"  {'_'*6} {'_'*40} {'_'*8} {'_'*10} {'_'*10}")

    for _, row in review_df.iterrows():
        rank = int(row["rank"])
        name = str(row["company_name"])[:40]
        score = row["total_score"]
        conf = row.get("revenue_confidence", "N/A")
        reviewed = "YES" if rank in reviewed_ranks else ""
        print(f"  {rank:<6} {name:<40} {score:<8} {conf}%{'':<5} {reviewed}")

    print(f"\n  To approve: python 09_review_queue.py --approve <rank>")
    print(f"  To reject:  python 09_review_queue.py --reject <rank>")


def approve_lead(df, rank, reason="Manual review: approved"):
    """Approve a lead by rank number."""
    log = load_review_log()

    target = df[df["rank"] == rank]
    if len(target) == 0:
        print(f"  [ERROR] No lead found at rank {rank}")
        return

    company = target.iloc[0]["company_name"]
    new_entry = pd.DataFrame([{
        "rank": rank,
        "company_name": company,
        "action": "APPROVED",
        "reason": reason,
        "reviewed_at": datetime.now().isoformat(),
    }])

    log = pd.concat([log, new_entry], ignore_index=True)
    save_review_log(log)

    # Update the scored file
    df.loc[df["rank"] == rank, "qualification"] = "QUALIFIED"
    df.to_csv(CHECKPOINT_SCORED, index=False, encoding="utf-8")

    print(f"  [APPROVED] Rank {rank}: {company}")
    print(f"  [APPROVED] Reason: {reason}")


def reject_lead(df, rank, reason="Manual review: rejected"):
    """Reject a lead by rank number."""
    log = load_review_log()

    target = df[df["rank"] == rank]
    if len(target) == 0:
        print(f"  [ERROR] No lead found at rank {rank}")
        return

    company = target.iloc[0]["company_name"]
    new_entry = pd.DataFrame([{
        "rank": rank,
        "company_name": company,
        "action": "REJECTED",
        "reason": reason,
        "reviewed_at": datetime.now().isoformat(),
    }])

    log = pd.concat([log, new_entry], ignore_index=True)
    save_review_log(log)

    # Update the scored file
    df.loc[df["rank"] == rank, "qualification"] = "DISQUALIFIED"
    df.to_csv(CHECKPOINT_SCORED, index=False, encoding="utf-8")

    print(f"  [REJECTED] Rank {rank}: {company}")
    print(f"  [REJECTED] Reason: {reason}")


def show_stats(df):
    """Show review statistics."""
    log = load_review_log()

    qualified = len(df[df["qualification"] == "QUALIFIED"])
    review_req = len(df[df["qualification"] == "REVIEW_REQUIRED"])
    disqualified = len(df[df.get("qualification", "") == "DISQUALIFIED"]) if "qualification" in df.columns else 0

    print(f"\n  Pipeline Statistics")
    print(f"  {'_'*40}")
    print(f"  Total scored leads:    {len(df)}")
    print(f"  QUALIFIED:             {qualified}")
    print(f"  REVIEW_REQUIRED:       {review_req}")
    print(f"  DISQUALIFIED:          {disqualified}")
    print(f"  Qualification threshold: {QUALIFICATION_THRESHOLD}")

    if len(log) > 0:
        approved = len(log[log["action"] == "APPROVED"])
        rejected = len(log[log["action"] == "REJECTED"])
        print(f"\n  Review Log")
        print(f"  {'_'*40}")
        print(f"  Reviews completed:     {len(log)}")
        print(f"  Approved:              {approved}")
        print(f"  Rejected:              {rejected}")

    # Score distribution
    print(f"\n  Score Distribution")
    print(f"  {'_'*40}")
    avg_score = df["total_score"].mean()
    median_score = df["total_score"].median()
    print(f"  Average score:         {avg_score:.1f}")
    print(f"  Median score:          {median_score:.1f}")
    print(f"  Min / Max:             {df['total_score'].min():.1f} / {df['total_score'].max():.1f}")


def main():
    parser = argparse.ArgumentParser(description="Human review queue for borderline leads")
    parser.add_argument("--approve", type=int, help="Approve lead at given rank")
    parser.add_argument("--reject", type=int, help="Reject lead at given rank")
    parser.add_argument("--reason", type=str, default="", help="Reason for approve/reject")
    parser.add_argument("--stats", action="store_true", help="Show review statistics")
    args = parser.parse_args()

    print("=" * 60)
    print(" STEP 9: HUMAN REVIEW QUEUE")
    print("=" * 60)

    df = load_scored()

    if args.stats:
        show_stats(df)
    elif args.approve:
        reason = args.reason or "Manual review: approved"
        approve_lead(df, args.approve, reason)
    elif args.reject:
        reason = args.reason or "Manual review: rejected"
        reject_lead(df, args.reject, reason)
    else:
        list_review_needed(df)


if __name__ == "__main__":
    main()
