# Step 3 — SQLite persistence + server-side question IDs

## Start session
SID=$(curl -s -X POST http://127.0.0.1:8000/session/start   -H "Content-Type: application/json"   -d @- << 'JSON' | jq -r '.session_id'
{
  "resume_text": "'"$(cat sample/sample_resume.txt)"'",
  "target_intro": "Targeting Data Analyst roles in ecommerce."
}
JSON
)
echo "SID=$SID"

## Get next question
curl -s "http://127.0.0.1:8000/session/$SID/next_question" | jq

## Answer (use returned .question.id)
QID=$(curl -s "http://127.0.0.1:8000/session/$SID/next_question" | jq -r '.question.id')
curl -s -X POST "http://127.0.0.1:8000/session/$SID/answer"   -H "Content-Type: application/json"   -d '{
    "question_id": "'"$QID"'",
    "answer_text": "I owned PySpark transforms and scheduling; intermediate level."
  }' | jq

## Profile
curl -s "http://127.0.0.1:8000/session/$SID/profile" | jq

## Synthesize
curl -s -X POST "http://127.0.0.1:8000/session/$SID/synthesize" | jq

## Toggle LLM mode (stubbed)
curl -s -X POST "http://127.0.0.1:8000/session/$SID/config?use_llm=true" | jq
