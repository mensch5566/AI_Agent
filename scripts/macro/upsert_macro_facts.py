"""Write macro facts to Obsidian JSON (SSOT) + upsert Supabase. Dry-run by default."""
from __future__ import annotations
import argparse, json, os
from pathlib import Path

from macro.fetch_fred import fetch_all

REPO_ROOT = Path(__file__).resolve().parents[2]
OBSIDIAN_DATA = Path.home() / "Obsidian" / "Khouse" / "Macro_Weekly" / "01_Source" / "Data"
BATCH_SIZE = 500


def write_local_json(rows: list[dict], out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"count": len(rows), "facts": rows}, ensure_ascii=False, indent=2))


def load_env() -> dict:
    env = {}
    p = REPO_ROOT / ".env"
    if p.exists():
        for line in p.read_text().splitlines():
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env[k] = v
    return env


def supabase_client():
    env = load_env()
    url = env.get("NEXT_PUBLIC_SUPABASE_URL") or env.get("SUPABASE_URL")
    key = env.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise SystemExit("Missing NEXT_PUBLIC_SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY in .env")
    from supabase import create_client
    return create_client(url, key)


def upsert(rows: list[dict]) -> int:
    client = supabase_client()
    total = 0
    for i in range(0, len(rows), BATCH_SIZE):
        chunk = rows[i:i + BATCH_SIZE]
        client.table("macro_facts").upsert(chunk).execute()
        total += len(chunk)
    return total


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="actually write to Supabase (default: dry-run)")
    args = ap.parse_args()

    key = os.environ.get("FRED_API_KEY") or load_env().get("FRED_API_KEY")
    if not key:
        raise SystemExit("Set FRED_API_KEY (env or .env)")

    rows = fetch_all(key)
    out = OBSIDIAN_DATA / "macro_facts.json"
    write_local_json(rows, out)
    print(f"[json] wrote {len(rows)} facts -> {out}")

    if not args.apply:
        keys = sorted({r["indicator_key"] for r in rows})
        print(f"[dry-run] would upsert {len(rows)} rows across {len(keys)} indicators: {keys}")
        print("[dry-run] re-run with --apply to write Supabase")
        return
    print(f"[apply] upserted {upsert(rows)} rows to macro_facts")


if __name__ == "__main__":
    main()
