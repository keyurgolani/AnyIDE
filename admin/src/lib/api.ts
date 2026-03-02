import { useAuthStore } from '@/store/authStore'

type AuthStoreLike = Pick<typeof useAuthStore, 'getState'>
type LocationLike = Pick<Location, 'pathname' | 'assign'>

interface APIOptions {
  authStore?: AuthStoreLike
  fetchImpl?: typeof fetch
  location?: LocationLike
}

export interface HITLRequest {
  id: string
  created_at: string
  tool_name: string
  tool_category: string
  request_params: Record<string, any>
  request_context: Record<string, any>
  policy_rule_matched: string
  status: 'pending' | 'approved' | 'rejected' | 'expired'
  reviewed_by?: string
  reviewed_at?: string
  reviewer_note?: string
  execution_result?: Record<string, any>
  ttl_seconds: number
}

export interface AuditLogEntry {
  id: string
  timestamp: string
  tool_name: string
  tool_category: string
  protocol: string
  status: string
  duration_ms?: number
  error_message?: string
  request_params?: Record<string, any>
  response?: Record<string, any>
}

export interface SystemHealth {
  uptime: number
  pending_hitl: number
  tools_executed: number
  error_rate: number
}

export interface DetailedHealth {
  uptime: number
  pending_hitl: number
  tools_executed: number
  error_rate: number
  memory_used_mb: number
  memory_total_mb: number
  memory_percent: number
  cpu_percent: number
  db_size_mb: number
  db_path: string
  workspace_size_mb: number
  workspace_path: string
  websocket_connections: number
  python_version: string
  platform: string
  version: string
}

export interface ToolSchema {
  name: string
  category: string
  description: string
  input_schema: Record<string, any>
  output_schema?: Record<string, any>
  requires_hitl: boolean
}

export interface ToolListResponse {
  tools: ToolSchema[]
  total: number
}

export interface ConfigResponse {
  auth_enabled: boolean
  workspace_path: string
  database_path: string
  log_level: string
  http_config: Record<string, any>
  policy_rules_count: number
  tool_configs: Record<string, any>
  llm_endpoints: LLMEndpointSummary[]
}

export interface LLMEndpointSummary {
  id: string
  provider: string
  base_url: string
  default_model: string
  timeout: number
  has_api_key: boolean
}

export interface LLMEndpointListResponse {
  endpoints: LLMEndpointSummary[]
  total: number
}

export interface LLMEndpointTestResponse {
  endpoint_id: string
  provider: string
  model: string
  success: boolean
  latency_ms?: number
  response_preview?: string
  error_type?: string
  error_message?: string
}

export interface AuditLogFilterResponse {
  logs: AuditLogEntry[]
  total: number
  filtered: number
}

export interface DashboardStats {
  tool_stats: Array<{ tool_category: string; count: number }>
  status_stats: Array<{ status: string; count: number }>
  hourly_stats: Array<{ hour: string; count: number }>
  duration_stats: Array<{ tool_category: string; tool_name: string; avg_duration_ms: number }>
  pending_hitl: number
}

export interface ContainerInfo {
  id: string
  name: string
  status: string
  image: string
  created: string
}

export interface ContainerLogs {
  logs: string
}

export interface SecretsInfo {
  keys: string[]
  count: number
  secrets_file: string
}

export interface SecretsReloadResponse {
  message: string
  count: number
  secrets_file: string
}

export class API {
  private handlingUnauthorized = false
  private authStore: AuthStoreLike
  private fetchImpl: typeof fetch
  private location: LocationLike

  constructor(options: APIOptions = {}) {
    this.authStore = options.authStore ?? useAuthStore
    this.fetchImpl =
      options.fetchImpl ??
      // Bind native fetch to window to avoid "Illegal invocation" when called as a class property method.
      (typeof window !== 'undefined' && typeof window.fetch === 'function'
        ? window.fetch.bind(window)
        : fetch)
    this.location = options.location ?? window.location
  }

  private getBaseUrl(): string {
    // Support deployments behind a path prefix, e.g. /myapp/admin/.
    const pathname = this.location.pathname || '/'
    const adminIndex = pathname.indexOf('/admin')
    const prefix = adminIndex > 0 ? pathname.slice(0, adminIndex) : ''
    return `${window.location.origin}${prefix}`
  }

  private handleUnauthorized() {
    if (this.handlingUnauthorized) return
    this.handlingUnauthorized = true

    this.authStore.getState().logout()

    // Force a navigation so protected routes are re-evaluated immediately.
    if (this.location.pathname !== '/admin/login') {
      this.location.assign('/admin/login')
    } else {
      this.handlingUnauthorized = false
    }
  }

  private async request(
    path: string,
    init?: RequestInit,
    options?: { skipAuthRedirect?: boolean }
  ): Promise<Response> {
    const headers = new Headers(init?.headers ?? {})
    const sessionToken = this.authStore.getState().sessionToken
    if (sessionToken && !headers.has('Authorization')) {
      headers.set('Authorization', `Bearer ${sessionToken}`)
    }

    const response = await this.fetchImpl(`${this.getBaseUrl()}${path}`, {
      credentials: 'include',
      ...init,
      headers,
    })

    if (response.status === 401 && !options?.skipAuthRedirect) {
      this.handleUnauthorized()
    }

    return response
  }

  async login(password: string): Promise<{ token: string }> {
    const response = await this.request(
      '/admin/api/login',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password }),
      },
      { skipAuthRedirect: true }
    )

    if (!response.ok) {
      if (response.status === 401) {
        throw new Error('Invalid password')
      }
      if (response.status === 404) {
        throw new Error('Login endpoint not found (404). Check URL/port and proxy path.')
      }
      throw new Error(`Login failed (${response.status})`)
    }

    return response.json()
  }

  async logout(): Promise<void> {
    await this.request('/admin/api/logout', {
      method: 'POST',
    })
  }

  async getAuditLogs(limit = 100): Promise<AuditLogEntry[]> {
    const response = await this.request(`/admin/api/audit?limit=${limit}`)

    if (!response.ok) {
      throw new Error('Failed to fetch audit logs')
    }

    return response.json()
  }

  async getFilteredAuditLogs(params: {
    limit?: number
    offset?: number
    status?: string
    tool_category?: string
    tool_name?: string
    protocol?: string
    start_time?: string
    end_time?: string
    search?: string
  }): Promise<AuditLogFilterResponse> {
    const searchParams = new URLSearchParams()
    if (params.limit) searchParams.set('limit', params.limit.toString())
    if (params.offset) searchParams.set('offset', params.offset.toString())
    if (params.status) searchParams.set('status', params.status)
    if (params.tool_category) searchParams.set('tool_category', params.tool_category)
    if (params.tool_name) searchParams.set('tool_name', params.tool_name)
    if (params.protocol) searchParams.set('protocol', params.protocol)
    if (params.start_time) searchParams.set('start_time', params.start_time)
    if (params.end_time) searchParams.set('end_time', params.end_time)
    if (params.search) searchParams.set('search', params.search)

    const response = await this.request(`/admin/api/audit/filtered?${searchParams}`)

    if (!response.ok) {
      throw new Error('Failed to fetch filtered audit logs')
    }

    return response.json()
  }

  async exportAuditLogs(format: 'json' | 'csv', params: {
    status?: string
    tool_category?: string
    start_time?: string
    end_time?: string
  }): Promise<Blob> {
    const searchParams = new URLSearchParams()
    searchParams.set('format', format)
    if (params.status) searchParams.set('status', params.status)
    if (params.tool_category) searchParams.set('tool_category', params.tool_category)
    if (params.start_time) searchParams.set('start_time', params.start_time)
    if (params.end_time) searchParams.set('end_time', params.end_time)

    const response = await this.request(`/admin/api/audit/export?${searchParams}`)

    if (!response.ok) {
      throw new Error('Failed to export audit logs')
    }

    return response.blob()
  }

  async getSystemHealth(): Promise<SystemHealth> {
    const response = await this.request('/admin/api/health')

    if (!response.ok) {
      throw new Error('Failed to fetch system health')
    }

    return response.json()
  }

  async getDetailedHealth(): Promise<DetailedHealth> {
    const response = await this.request('/admin/api/health/detailed')

    if (!response.ok) {
      throw new Error('Failed to fetch detailed health')
    }

    return response.json()
  }

  async getTools(): Promise<ToolListResponse> {
    const response = await this.request('/admin/api/tools')

    if (!response.ok) {
      throw new Error('Failed to fetch tools')
    }

    return response.json()
  }

  async getToolSchema(category: string, name: string): Promise<ToolSchema> {
    const response = await this.request(`/admin/api/tools/${category}/${name}`)

    if (!response.ok) {
      throw new Error('Failed to fetch tool schema')
    }

    return response.json()
  }

  async getConfig(): Promise<ConfigResponse> {
    const response = await this.request('/admin/api/config')

    if (!response.ok) {
      throw new Error('Failed to fetch config')
    }

    return response.json()
  }

  async getLLMEndpoints(): Promise<LLMEndpointListResponse> {
    const response = await this.request('/admin/api/llm/endpoints')

    if (!response.ok) {
      throw new Error('Failed to fetch LLM endpoints')
    }

    return response.json()
  }

  async testLLMEndpoint(endpointId: string, prompt?: string): Promise<LLMEndpointTestResponse> {
    const response = await this.request('/admin/api/llm/test', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        endpoint_id: endpointId,
        ...(prompt ? { prompt } : {}),
      }),
    })

    if (!response.ok) {
      throw new Error('Failed to test LLM endpoint')
    }

    return response.json()
  }

  async getDashboardStats(): Promise<DashboardStats> {
    const response = await this.request('/admin/api/stats')

    if (!response.ok) {
      throw new Error('Failed to fetch dashboard stats')
    }

    return response.json()
  }

  async getContainers(): Promise<ContainerInfo[]> {
    const response = await this.request('/admin/api/containers')

    if (!response.ok) {
      throw new Error('Failed to fetch containers')
    }

    const payload: unknown = await response.json()

    // Backward/forward compatibility: some backends return an array, others wrap it.
    if (Array.isArray(payload)) {
      return payload as ContainerInfo[]
    }
    if (
      payload &&
      typeof payload === 'object' &&
      Array.isArray((payload as { containers?: unknown }).containers)
    ) {
      return (payload as { containers: ContainerInfo[] }).containers
    }

    throw new Error('Invalid container list response')
  }

  async getContainerLogs(containerId: string, tail = 100): Promise<ContainerLogs> {
    const response = await this.request(`/admin/api/containers/${containerId}/logs?tail=${tail}`)

    if (!response.ok) {
      throw new Error('Failed to fetch container logs')
    }

    return response.json()
  }

  async getSecrets(): Promise<SecretsInfo> {
    const response = await this.request('/admin/api/secrets')

    if (!response.ok) {
      throw new Error('Failed to fetch secrets')
    }

    return response.json()
  }

  async reloadSecrets(): Promise<SecretsReloadResponse> {
    const response = await this.request('/admin/api/secrets/reload', {
      method: 'POST',
    })

    if (!response.ok) {
      throw new Error('Failed to reload secrets')
    }

    return response.json()
  }
}

export const api = new API()
