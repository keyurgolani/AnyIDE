import { HITLRequest } from './api'

type WebSocketMessage = 
  | { type: 'hitl_request'; data: HITLRequest }
  | { type: 'hitl_update'; data: HITLRequest }
  | { type: 'pending_requests'; data: HITLRequest[] }
  | { type: 'decision_accepted'; data: { id: string; decision: string } }
  | { type: 'error'; data: { message: string } }

type MessageHandler = (message: WebSocketMessage) => void

export class WebSocketClient {
  private ws: WebSocket | null = null
  private handlers: Set<MessageHandler> = new Set()
  private reconnectTimeout: number | null = null
  private reconnectDelay = 1000
  private maxReconnectDelay = 30000
  private isConnecting = false
  private pendingMessages: any[] = []

  connect() {
    // Prevent multiple simultaneous connections
    if (this.ws?.readyState === WebSocket.OPEN || this.isConnecting) {
      console.log('WebSocket already connected or connecting')
      return
    }
    
    this.isConnecting = true
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const host = window.location.host
    const pathname = window.location.pathname || '/'
    const adminIndex = pathname.indexOf('/admin')
    const prefix = adminIndex > 0 ? pathname.slice(0, adminIndex) : ''
    const wsUrl = `${protocol}//${host}${prefix}/ws/hitl`
    
    this.ws = new WebSocket(wsUrl)
    
    this.ws.onopen = () => {
      console.log('WebSocket connected')
      this.reconnectDelay = 1000
      this.isConnecting = false

      // Flush messages queued while the connection was opening.
      if (this.pendingMessages.length > 0 && this.ws?.readyState === WebSocket.OPEN) {
        for (const message of this.pendingMessages) {
          this.ws.send(JSON.stringify(message))
        }
        this.pendingMessages = []
      }
    }
    
    this.ws.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data) as WebSocketMessage
        this.handlers.forEach(handler => handler(message))
      } catch (error) {
        console.error('Failed to parse WebSocket message:', error)
      }
    }
    
    this.ws.onerror = (error) => {
      console.error('WebSocket error:', error)
      this.isConnecting = false
    }
    
    this.ws.onclose = () => {
      console.log('WebSocket disconnected')
      this.isConnecting = false
      this.scheduleReconnect()
    }
  }

  isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN
  }

  private scheduleReconnect() {
    if (this.reconnectTimeout) {
      return
    }
    
    this.reconnectTimeout = window.setTimeout(() => {
      this.reconnectTimeout = null
      this.connect()
      this.reconnectDelay = Math.min(this.reconnectDelay * 2, this.maxReconnectDelay)
    }, this.reconnectDelay)
  }

  disconnect() {
    if (this.reconnectTimeout) {
      clearTimeout(this.reconnectTimeout)
      this.reconnectTimeout = null
    }
    
    if (this.ws) {
      this.ws.close()
      this.ws = null
    }
  }

  send(message: any) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(message))
      return
    }

    this.pendingMessages.push(message)

    if (!this.isConnecting) {
      this.connect()
    }
  }

  onMessage(handler: MessageHandler) {
    this.handlers.add(handler)
    return () => this.handlers.delete(handler)
  }

  approveRequest(id: string, note?: string) {
    this.send({
      type: 'hitl_decision',
      data: { id, decision: 'approve', note },
    })
  }

  rejectRequest(id: string, note?: string) {
    this.send({
      type: 'hitl_decision',
      data: { id, decision: 'reject', note },
    })
  }

  requestPendingRequests() {
    this.send({
      type: 'request_pending',
    })
  }
}

export const wsClient = new WebSocketClient()
