# SSE Server - Real-time Chat Message Push

## Overview

SSE Server is a standalone service that provides real-time message push for chat conversations using Server-Sent Events (SSE) protocol.

## Architecture

```
User A sends message → Chat System → HTTP callback → SSE Server → Push to User B
                                              ↓ (fallback)
                                          Outbox polling
```

## Features

- **Real-time push**: Messages delivered instantly via SSE
- **Connection management**: Track online users per conversation
- **Heartbeat**: Keep connections alive with 30-second heartbeat
- **Auto-reconnect**: Browser EventSource automatically reconnects
- **Stats API**: Monitor connection counts and distribution

## Endpoints

### SSE Endpoint (Frontend)

```
GET /sse/chat/{caseId}?participant_id={userId}
```

**Response**: `text/event-stream`

**Events**:
- `connected`: Connection confirmation
- `message`: New message notification
- `heartbeat`: Keepalive signal

**Example**:
```javascript
const eventSource = new EventSource('http://localhost:8081/sse/chat/case-123?participant_id=user-a')

eventSource.addEventListener('message', (e) => {
  const data = JSON.parse(e.data)
  console.log('New message:', data)
})
```

### Internal Push Endpoint (Backend)

```
POST /internal/push
```

**Request body**:
```json
{
  "case_id": "case-123",
  "conversation_id": "conv-abc",
  "message_id": 456,
  "author_id": "user-a",
  "body": "Hello!",
  "source": "user",
  "channel_key": "main_group"
}
```

**Response**:
```json
{
  "success": true,
  "pushed": 2,
  "online_users": ["user-b", "user-c"]
}
```

### Stats Endpoint

```
GET /internal/stats
```

**Response**:
```json
{
  "total_connections": 50,
  "total_cases": 10,
  "connections_per_case": {
    "case-123": 3,
    "case-456": 5
  }
}
```

### Health Check

```
GET /health
```

**Response**:
```json
{
  "status": "healthy",
  "service": "sse-server"
}
```

## Configuration

Environment variables:

- `SSE_SERVER_HOST`: Server host (default: `127.0.0.1`)
- `SSE_SERVER_PORT`: Server port (default: `8081`)
- `SSE_SERVER_LOG_LEVEL`: Log level (default: `INFO`)
- `MAX_CONNECTIONS`: Maximum concurrent connections (default: `1000`)
- `HEARTBEAT_INTERVAL`: Heartbeat interval in seconds (default: `30`)

## Running

### Local Development

```bash
cd external-systems/sse-server
pip install -r requirements.txt
python -m sse_server --host 127.0.0.1 --port 8081
```

### With Docker

```bash
docker build -t sse-server .
docker run -p 8081:8081 sse-server
```

## Integration

### Frontend (chat-page.tsx)

Replace 30-second polling with EventSource:

```typescript
const eventSource = new EventSource(`${SSE_URL}/sse/chat/${caseId}?participant_id=${userId}`)

eventSource.addEventListener('message', (e) => {
  const data = JSON.parse(e.data)
  if (data.type === 'new_message') {
    // Fetch full timeline and update UI
    await fetchAndUpdateMessages()
  }
})
```

### Backend (conversations.py)

After message commit, call SSE server:

```python
await notify_sse_server_push({
  'case_id': case_id,
  'message_id': message_id,
  'author_id': author_id,
  'body': body,
  'source': source,
})
```

## Monitoring

- Connection stats: `/internal/stats`
- Health check: `/health`
- Logs: stdout with timestamps

## Performance

- **Latency**: < 500ms from send to receive
- **Concurrency**: Supports 1000+ simultaneous connections
- **Memory**: ~100MB for 100 connections

## Fallback

If SSE server is unavailable:
- Frontend falls back to 30-second polling
- EventSource auto-reconnects when server restarts

## License

MIT