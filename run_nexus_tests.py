import subprocess
import sys

cmd = [sys.executable, '-m', 'pytest']
result = subprocess.run(cmd)
raise SystemExit(result.returncode)
