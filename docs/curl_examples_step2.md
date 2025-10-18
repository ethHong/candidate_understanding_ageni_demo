# Step 2 — Conversation Flow (cURL)

# 1) Start a session
curl -s -X POST http://127.0.0.1:8000/session/start   -H "Content-Type: application/json"   -d @- << 'JSON' | jq
{
  "resume_text": "$(cat sample/sample_resume.txt)",
  "target_intro": "Targeting Data Analyst roles in ecommerce."
}
JSON

# Response has: session_id, profile, next_question
# NOTE: For MVP, encode gap info in question_id yourself like: "<uuid>|skill_depth|Python"

# 2) Ask for next question
# Replace <SID> from step 1
curl -s http://127.0.0.1:8000/session/<SID>/next_question | jq

# 3) Send an answer (MVP encoding for gap)
# Example: qid="abc123|skill_depth|Python"
curl -s -X POST http://127.0.0.1:8000/session/<SID>/answer   -H "Content-Type: application/json"   -d '{
    "question_id": "abc123|skill_depth|Python",
    "answer_text": "I use Python weekly for data munging and API clients; I would say intermediate."
  }' | jq

# 4) Get current profile
curl -s http://127.0.0.1:8000/session/<SID>/profile | jq

# 5) Synthesize a human-readable summary
curl -s -X POST http://127.0.0.1:8000/session/<SID>/synthesize | jq
