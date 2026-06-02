#!/bin/bash
cd /Users/busiji/memory
TOKEN=$(git remote get-url gitlab | sed 's/.*:\([^@]*\)@.*/\1/')

# Get all files in project-map/
FILES=$(find project-map -type f 2>/dev/null)

for f in $FILES; do
  echo "Pushing: $f"
  CONTENT=$(cat "$f" | base64)
  python3 -c "
import http.client, json, base64, sys

token = '$TOKEN'
path = '$f'
content_b64 = sys.stdin.read().strip()

payload = {
    'branch': 'migrate-memory-to-root',
    'commit_message': f'修复: project-map 迁移到 repo 根目录 - $f',
    'actions': [{'action': 'create' if not __import__('os').path.exists(path) or __import__('os').path.isdir(path) else 'update', 'file_path': path, 'content': content_b64, 'encoding': 'base64'}]
}

conn = http.client.HTTPConnection('node-REDACTED.ts.net', timeout=30)
headers = {'PRIVATE-TOKEN': token, 'Content-Type': 'application/json'}
conn.request('POST', '/api/v4/projects/4/repository/commits', body=json.dumps(payload), headers=headers)
resp = conn.getresponse()
body = resp.read().decode()
if resp.status == 200:
    data = json.loads(body)
    print(f'  OK: {data.get(\"short_id\", \"?\")}')
else:
    print(f'  FAIL: {resp.status} {body[:100]}')
conn.close()
" <<< "$CONTENT"
done
