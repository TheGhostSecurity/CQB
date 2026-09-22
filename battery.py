import subprocess, sys, os
from pathlib import Path
CQ = Path(r"C:\Users\ghost\Desktop\CQB")
PY = sys.executable

def run(cmd, cwd=None, timeout=600):
    p = subprocess.run(cmd, cwd=cwd or CQ, capture_output=True, text=True, timeout=timeout)
    return p.returncode, (p.stdout or "") + (p.stderr or "")

# 1) THE runtime check (import must RUN, not just compile)
rc, out = run([PY, "-c",
  "from ursina.prefabs.first_person_controller import FirstPersonController;"
  "print('RUNTIME_FPC_OK')"])
print("STEP1 runtime import -> rc=%s %s" % (rc, out.strip()[-60:]))

# 2) compile the game file
rc, out = run([PY, "-m", "py_compile", "gate_ursina.py"])
print("STEP2 py_compile -> rc=%s" % rc)

# 3) rebuild with the EXISTING spec (same one that froze your rifle)
if not (CQ / "dist" / "CQB_M4A1_Gate.exe").exists():
    print("WARNING: no previous build; doing full spec build (slow)")
rc, out = run([PY, "-m", "PyInstaller", "--noconfirm", "--clean",
               "CQB_M4A1_Gate.spec"])
severity = [ln for ln in out.splitlines() if "ERROR" in ln or "error:" in ln]
print("STEP3 build -> rc=%s errors=%d" % (rc, len(severity)))
if severity:
    print("\n".join(severity[:5]))

exe = CQ / "dist" / "CQB_M4A1_Gate.exe"
print("STEP4 exe -> exists=%s size=%.1fMB" % (exe.exists(),
      exe.stat().st_size/1e6 if exe.exists() else 0))
