import { AuditLogEntry } from './api'

type LogsWebSocketMessage =
  | { type: 'initial_logs'; data: AuditLogEntry[] }
  | { type: 'new_logs'; data: AuditLogEntry[] }
  | { type: 'logs'; data: AuditLogEntry[] }
  | { type: 'error'; data: { message: string } }

type LogsMessageHandler = (message: LogsWebSocketMessage) => void

export class LogsWebSocketClient {
  private ws: WebSocket | null = null
  private handlers: Set<LogsMessageHandler> = new Set()
  private reconnectTimeout: number | null = null
  private reconnectDelay = 1000
  private maxReconnectDelay = 30000
  private isConnecting = false

  connect(): Promise<boolean> {
    return new Promise((resolve) => {
      // Prevent multiple simultaneous connections
      if (this.ws?.readyState === WebSocket.OPEN) {
        resolve(true)
        return
      }

      if (this.isConnecting) {
        resolve(false)
        return
      }

      this.isConnecting = true
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
      const host = window.location.host
      const wsUrl = `${protocol}//${host}/ws/logs`

      this.ws = new WebSocket(wsUrl)

      this.ws.onopen = () => {
        console.log('Logs WebSocket connected')
        this.reconnectDelay = 1000
        this.isConnecting = false
        resolve(true)
      }

      this.ws.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data) as LogsWebSocketMessage
          this.handlers.forEach(handler => handler(message))
        } catch (error) {
          console.error('Failed to parse logs WebSocket message:', error)
        }
      }

      this.ws.onerror = (error) => {
        console.error('Logs WebSocket error:', error)
        this.isConnecting = false
        resolve(false)
      }

      this.ws.onclose = () => {
        console.log('Logs WebSocket disconnected')
        this.isConnecting = false
        this.scheduleReconnect()
      }

      // Timeout for connection
      setTimeout(() => {
        if (this.isConnecting) {
          this.isConnecting = false
          resolve(false)
        }
      }, 5000)
    })
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

  subscribe(pollInterval = 2) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({
        type: 'subscribe',
        poll_interval: pollInterval,
      }))
    }
  }

  unsubscribe() {
    // Close connection to stop subscription
    this.disconnect()
  }

  requestLogs(limit = 50, category?: string, status?: string) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({
        type: 'get_logs',
        limit,
        category,
        status,
      }))
    }
  }

  onMessage(handler: LogsMessageHandler): () => void {
    this.handlers.add(handler)
    return () => this.handlers.delete(handler)
  }
}

export const logsWsClient = new LogsWebSocketClient()
