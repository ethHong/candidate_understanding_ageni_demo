# cURL Examples

## Health
curl -s http://127.0.0.1:8000/health | jq

## Parse resume (text)
curl -s -X POST http://127.0.0.1:8000/parse_resume \
  -H "Content-Type: application/json" \
  -d @- << 'JSON' | jq
{
  "resume_text": "$(cat sample/sample_resume.txt)",
  "target_intro": "Targeting Data Analyst roles in ecommerce and sports analytics."
}
JSON

## Parse resume (file)
curl -s -X POST http://127.0.0.1:8000/parse_resume_file \
  -F "file=@sample/sample_resume.txt" \
  -F 'target_intro=Targeting Data Analyst roles' | jq
