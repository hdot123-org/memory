#!/bin/bash
# op-mcp.sh — 1Password MCP client for webhook scripts
# Uses Streamable HTTP MCP protocol to talk to 1password-connect-mcp server
# Eliminates Touch ID dependency in launchd environment

OP_MCP_URL="http://192.168.88.11:9080/mcp/1password"
OP_VAULT_SEVER="ozqqpvh5yvvxvyu64npq62a3ti"

_op_mcp_read_key() {
    /opt/homebrew/bin/python3 -c "
import json, sys
try:
    with open('$HOME/.factory/mcp.json') as f:
        cfg = json.load(f)
    key = cfg['mcpServers']['1password-connect']['headers']['apikey']
    if not key:
        print('MCP_CONFIG_MISSING', file=sys.stderr)
        sys.exit(1)
    print(key)
except (KeyError, FileNotFoundError, json.JSONDecodeError) as e:
    print('MCP_CONFIG_MISSING', file=sys.stderr)
    sys.exit(1)
except Exception as e:
    print(f'MCP_CONFIG_MISSING', file=sys.stderr)
    sys.exit(1)
"
}

# Get a field value from a 1Password item via MCP
# Usage: op_get_field <vault_id> <item_id> <field_label>
op_get_field() {
    local vault_id="$1"
    local item_id="$2"
    local field_label="$3"
    local api_key
    api_key=$(_op_mcp_read_key)

    if [ -z "$api_key" ]; then
        return 1
    fi

    /opt/homebrew/bin/python3 -c "
import json, urllib.request, urllib.error, sys, socket

socket.setdefaulttimeout(15)

api_key = '''$api_key'''
url = '$OP_MCP_URL'

def mcp_post(payload, sid=None):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, method='POST')
    req.add_header('Content-Type', 'application/json')
    req.add_header('Accept', 'application/json, text/event-stream')
    req.add_header('apikey', api_key)
    if sid:
        req.add_header('Mcp-Session-Id', sid)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            new_sid = resp.headers.get('Mcp-Session-Id', '')
            body = resp.read().decode()
            for line in body.split('\\n'):
                if line.startswith('data: '):
                    return json.loads(line[6:]), new_sid
            return json.loads(body) if body.strip() else {}, new_sid
    except urllib.error.HTTPError as e:
        if e.code == 202:
            return {}, sid
        raise

try:
    # Step 1: Initialize (get session ID)
    _, session_id = mcp_post({
        'jsonrpc': '2.0',
        'method': 'initialize',
        'params': {
            'protocolVersion': '2025-03-26',
            'capabilities': {},
            'clientInfo': {'name': 'op-mcp-sh', 'version': '1.0'}
        },
        'id': 1
    })

    # Step 2: Send initialized notification
    mcp_post({
        'jsonrpc': '2.0',
        'method': 'notifications/initialized'
    }, session_id)

    # Step 3: Call read_secret tool
    result, _ = mcp_post({
        'jsonrpc': '2.0',
        'method': 'tools/call',
        'params': {
            'name': 'read_secret',
            'arguments': {
                'vault_id': '$vault_id',
                'item_id': '$item_id',
                'field_label': '$field_label'
            }
        },
        'id': 2
    }, session_id)

    if result.get('result', {}).get('isError'):
        print('MCP_TOOL_ERROR: ' + str(result['result'].get('content', [{}])[0].get('text', 'unknown')), file=sys.stderr)
        sys.exit(1)

    for c in result.get('result', {}).get('content', []):
        if c.get('type') == 'text':
            val = c['text'].strip()
            if val:
                print(val)
                sys.exit(0)
    print('MCP_FIELD_NOT_FOUND', file=sys.stderr)
    sys.exit(1)
except urllib.error.HTTPError as e:
    print(f'MCP_HTTP_{e.code}', file=sys.stderr)
    sys.exit(1)
except (urllib.error.URLError, TimeoutError, socket.timeout, OSError) as e:
    print('MCP_TIMEOUT', file=sys.stderr)
    sys.exit(1)
except SystemExit:
    raise
except Exception as e:
    print('MCP_ERROR: {}: {}'.format(type(e).__name__, e), file=sys.stderr)
    sys.exit(1)
"
}
