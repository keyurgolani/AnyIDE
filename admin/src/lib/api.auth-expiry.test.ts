import { beforeEach, describe, expect, it, vi } from 'vitest'

import { API } from './api'
import { useAuthStore } from '@/store/authStore'

describe('admin API session expiry handling', () => {
  beforeEach(() => {
    localStorage.clear()
    useAuthStore.setState({ isAuthenticated: false, sessionToken: null })
    vi.restoreAllMocks()
  })

  it('logs out and redirects to /admin/login on 401 from protected endpoints', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(new Response(null, { status: 401 }))
    const locationAssignSpy = vi.fn()
    const api = new API({
      fetchImpl: fetchMock as typeof fetch,
      location: {
        pathname: '/admin',
        assign: locationAssignSpy,
      },
    })

    useAuthStore.getState().login('fake-session-token')

    await expect(api.getSystemHealth()).rejects.toThrow('Failed to fetch system health')

    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(useAuthStore.getState().isAuthenticated).toBe(false)
    expect(useAuthStore.getState().sessionToken).toBeNull()
    expect(locationAssignSpy).toHaveBeenCalledWith('/admin/login')
  })

  it('does not redirect when login itself returns 401', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(new Response(null, { status: 401 }))
    const locationAssignSpy = vi.fn()
    const api = new API({
      fetchImpl: fetchMock as typeof fetch,
      location: {
        pathname: '/admin/login',
        assign: locationAssignSpy,
      },
    })

    await expect(api.login('wrong-password')).rejects.toThrow('Invalid password')

    expect(locationAssignSpy).not.toHaveBeenCalled()
  })

  it('sends bearer token from auth store on protected requests', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(
      new Response(JSON.stringify({ uptime: 1, pending_hitl: 0, tools_executed: 0, error_rate: 0 }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })
    )
    const api = new API({
      fetchImpl: fetchMock as typeof fetch,
    })

    useAuthStore.getState().login('stored-session-token')

    await api.getSystemHealth()

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [, init] = fetchMock.mock.calls[0]
    const headers = new Headers(init?.headers as HeadersInit)
    expect(headers.get('Authorization')).toBe('Bearer stored-session-token')
  })

  it('includes URL prefix before /admin when app is served from a subpath', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(new Response(null, { status: 401 }))
    const api = new API({
      fetchImpl: fetchMock as typeof fetch,
      location: {
        pathname: '/myapp/admin/login',
        assign: vi.fn(),
      },
    })

    await expect(api.login('wrong-password')).rejects.toThrow('Invalid password')

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url] = fetchMock.mock.calls[0]
    expect(url).toBe('http://localhost:3000/myapp/admin/api/login')
  })

  it('binds native fetch to window to avoid illegal invocation', async () => {
    const originalWindowFetch = window.fetch
    const originalGlobalFetch = globalThis.fetch
    const locationAssignSpy = vi.fn()

    const nativeLikeFetch = vi.fn(function (this: any) {
      if (this !== window) {
        throw new TypeError("Failed to execute 'fetch' on 'Window': Illegal invocation")
      }
      return Promise.resolve(new Response(null, { status: 401 }))
    }) as unknown as typeof fetch

    ;(window as any).fetch = nativeLikeFetch
    ;(globalThis as any).fetch = nativeLikeFetch

    try {
      const api = new API({
        location: {
          pathname: '/admin/login',
          assign: locationAssignSpy,
        },
      })

      await expect(api.login('wrong-password')).rejects.toThrow('Invalid password')
      expect(nativeLikeFetch).toHaveBeenCalledTimes(1)
      expect(locationAssignSpy).not.toHaveBeenCalled()
    } finally {
      ;(window as any).fetch = originalWindowFetch
      ;(globalThis as any).fetch = originalGlobalFetch
    }
  })

  it('normalizes containers endpoint object payload into a container array', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          containers: [
            {
              id: 'abc123',
              name: 'web',
              status: 'running',
              image: 'nginx:latest',
              created: '2026-03-01T00:00:00Z',
            },
          ],
          total_count: 1,
        }),
        {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }
      )
    )
    const api = new API({
      fetchImpl: fetchMock as typeof fetch,
    })

    const containers = await api.getContainers()

    expect(Array.isArray(containers)).toBe(true)
    expect(containers).toHaveLength(1)
    expect(containers[0].name).toBe('web')
  })
})
