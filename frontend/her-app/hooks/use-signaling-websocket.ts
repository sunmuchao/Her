/**
 * WebSocket signaling channel for WebRTC calls
 */

import { useEffect, useRef, useState, useCallback } from 'react'

export type SignalingMessage = {
  type: 'join_room' | 'leave_room' | 'offer' | 'answer' | 'ice_candidate' | 'user_joined' | 'user_left' | 'room_joined' | 'error'
  call_id?: string
  user_id?: string
  from_user_id?: string
  participants?: string[]
  payload?: {
    sdp?: RTCSessionDescriptionInit
    candidate?: RTCIceCandidateInit
    target_user_id?: string
  }
  error?: string
}

export type UseSignalingWebSocketOptions = {
  signalingServerUrl: string
  userId: string
  onMessage?: (message: SignalingMessage) => void
  onConnected?: () => void
  onDisconnected?: () => void
  onError?: (error: string) => void
}

export function useSignalingWebSocket({
  signalingServerUrl,
  userId,
  onMessage,
  onConnected,
  onDisconnected,
  onError,
}: UseSignalingWebSocketOptions) {
  const [isConnected, setIsConnected] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimeoutRef = useRef<number | null>(null)

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      return
    }

    const wsUrl = `${signalingServerUrl}/ws/${userId}`
    const ws = new WebSocket(wsUrl)

    ws.onopen = () => {
      setIsConnected(true)
      console.log('[SignalingWebSocket] Connected to', wsUrl)
      onConnected?.()
    }

    ws.onclose = () => {
      setIsConnected(false)
      console.log('[SignalingWebSocket] Disconnected')
      onDisconnected?.()

      // 自动重连（3秒后）
      if (reconnectTimeoutRef.current === null) {
        reconnectTimeoutRef.current = window.setTimeout(() => {
          reconnectTimeoutRef.current = null
          connect()
        }, 3000)
      }
    }

    ws.onerror = (event) => {
      console.error('[SignalingWebSocket] Error:', event)
      onError?.('WebSocket connection error')
    }

    ws.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data) as SignalingMessage
        console.log('[SignalingWebSocket] Received:', message.type)
        onMessage?.(message)
      } catch (e) {
        console.error('[SignalingWebSocket] Failed to parse message:', e)
      }
    }

    wsRef.current = ws
  }, [signalingServerUrl, userId, onMessage, onConnected, onDisconnected, onError])

  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current !== null) {
      clearTimeout(reconnectTimeoutRef.current)
      reconnectTimeoutRef.current = null
    }
    if (wsRef.current) {
      wsRef.current.close()
      wsRef.current = null
    }
    setIsConnected(false)
  }, [])

  const send = useCallback((message: SignalingMessage) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(message))
      console.log('[SignalingWebSocket] Sent:', message.type)
    } else {
      console.warn('[SignalingWebSocket] Cannot send, not connected')
    }
  }, [])

  // 自动连接
  useEffect(() => {
    if (userId && signalingServerUrl) {
      connect()
    }
    return () => disconnect()
  }, [userId, signalingServerUrl, connect, disconnect])

  return {
    isConnected,
    connect,
    disconnect,
    send,
  }
}