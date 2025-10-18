from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)

def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"

def test_parse_resume():
    resume_text = "Product Manager at Hyperconnect. Built experimentation dashboards using SQL and Tableau. Used Python for analysis. No PyTorch."
    payload = {"resume_text": resume_text, "target_intro": "Targeting Data Analyst roles in ecommerce."}
    r = client.post("/parse_resume", json=payload)
    assert r.status_code == 200
    data = r.json()
    assert "profile_draft" in data
    skills = [s["name"] for s in data["profile_draft"]["skills"]]
    assert "SQL" in skills
    assert "Python" in skills
