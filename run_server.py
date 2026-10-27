import uvicorn
import sys
import os

# Add root directory to python path
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

if __name__ == "__main__":
    print("================================================================")
    print(" SAP Replication Server Monitor (SRSMon 15.7) - DBA Suite")
    print(" Starting server on http://localhost:8000")
    print("================================================================")
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=False)
