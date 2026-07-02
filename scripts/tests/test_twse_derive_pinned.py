"""twse-derive is PINNED during the derive-A migration: it reads pre-rename
TW uni_account keys and would silently misread renamed facts (spec §7/§10)."""
import subprocess, sys

SCRIPT = "/Users/mensch5566/CC_Switch_Config/skills/twse-derive/derive_twse.py"

def test_twse_derive_exits_3_with_pointer():
    r = subprocess.run([sys.executable, SCRIPT, "3081"],
                       capture_output=True, text=True)
    assert r.returncode == 3
    assert "derive-market-agnostic" in (r.stderr + r.stdout)
