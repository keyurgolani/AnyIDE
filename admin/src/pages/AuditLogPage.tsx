import { useState, useEffect, useCallback, useRef } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { FileText, Search, Download, X, ChevronLeft, ChevronRight, Wifi, WifiOff, RefreshCw } from 'lucide-react'
import { api } from '@/lib/api'
import { logsWsClient } from '@/lib/logsWebSocket'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { formatTimestamp, formatDuration, getStatusBadgeClass } from '@/lib/utils'

export default function AuditLogPage() {
  const [searchTerm, setSearchTerm] = useState('')
  const [statusFilter, setStatusFilter] = useState<string>('all')
  const [categoryFilter, setCategoryFilter] = useState<string>('all')
  const [page, setPage] = useState(0)
  const [pageSize] = useState(50)
  const [showExport, setShowExport] = useState(false)
  const [exportFormat, setExportFormat] = useState<'json' | 'csv'>('json')
  const [isExporting, setIsExporting] = useState(false)
  const [isWsConnected, setIsWsConnected] = useState(false)
  const [isPolling, setIsPolling] = useState(false)
  const [newLogsCount, setNewLogsCount] = useState(0)
  const queryClient = useQueryClient()
  const pollingIntervalRef = useRef<number | null>(null)

  // Primary data fetch with React Query
  const { data: logsData, isLoading, refetch } = useQuery({
    queryKey: ['audit-logs-filtered', searchTerm, statusFilter, categoryFilter, page],
    queryFn: () => api.getFilteredAuditLogs({
      limit: pageSize,
      offset: page * pageSize,
      status: statusFilter !== 'all' ? statusFilter : undefined,
      tool_category: categoryFilter !== 'all' ? categoryFilter : undefined,
      search: searchTerm || undefined,
    }),
    refetchInterval: false, // We handle real-time updates via websocket or fallback polling
  })

  // WebSocket connection and message handling
  useEffect(() => {
    let unsubscribe: (() => void) | null = null

    const connectWebSocket = async () => {
      const connected = await logsWsClient.connect()
      setIsWsConnected(connected)

      if (connected) {
        // Subscribe to log updates
        logsWsClient.subscribe(2)

        // Set up message handler
        unsubscribe = logsWsClient.onMessage((message) => {
          if (message.type === 'initial_logs' || message.type === 'new_logs') {
            // When filters are active, just invalidate the query to refetch
            if (statusFilter !== 'all' || categoryFilter !== 'all' || searchTerm) {
              queryClient.invalidateQueries({ queryKey: ['audit-logs-filtered'] })
            } else if (message.type === 'new_logs' && page === 0) {
              // Only show new logs indicator if on first page with no filters
              setNewLogsCount((prev) => prev + message.data.length)
            } else if (message.type === 'initial_logs') {
              // Initial logs loaded - refresh the data
              queryClient.invalidateQueries({ queryKey: ['audit-logs-filtered'] })
            }
          }
        })
      } else {
        // Fall back to polling if WebSocket fails
        startPolling()
      }
    }

    const startPolling = () => {
      setIsPolling(true)
      if (pollingIntervalRef.current) {
        clearInterval(pollingIntervalRef.current)
      }
      pollingIntervalRef.current = window.setInterval(() => {
        refetch()
      }, 5000)
    }

    connectWebSocket()

    return () => {
      if (unsubscribe) {
        unsubscribe()
      }
      logsWsClient.unsubscribe()
      if (pollingIntervalRef.current) {
        clearInterval(pollingIntervalRef.current)
      }
    }
  }, [queryClient, statusFilter, categoryFilter, searchTerm, page, refetch])

  // Handle refresh button click
  const handleRefresh = useCallback(() => {
    setNewLogsCount(0)
    refetch()
  }, [refetch])

  // Handle showing new logs
  const handleShowNewLogs = useCallback(() => {
    setNewLogsCount(0)
    refetch()
  }, [refetch])

  const logs = logsData?.logs || []
  const total = logsData?.total || 0
  const filtered = logsData?.filtered || 0
  const totalPages = Math.ceil(total / pageSize)

  const handleExport = async () => {
    setIsExporting(true)
    try {
      const blob = await api.exportAuditLogs(exportFormat, {
        status: statusFilter !== 'all' ? statusFilter : undefined,
        tool_category: categoryFilter !== 'all' ? categoryFilter : undefined,
      })

      // Create download link
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `audit_logs_${new Date().toISOString().slice(0, 19).replace(/[:-]/g, '')}.${exportFormat}`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
      setShowExport(false)
    } catch (error) {
      console.error('Export failed:', error)
    } finally {
      setIsExporting(false)
    }
  }

  // Get unique categories from the logs
  const categories = [...new Set(logs.map((log) => log.tool_category))]

  return (
    <div className="space-y-4 md:space-y-6">
      {/* Page Header */}
      <motion.div
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex flex-col md:flex-row md:items-center md:justify-between gap-4"
      >
        <div>
          <h1 className="text-3xl md:text-4xl font-bold gradient-text mb-2">Audit Log</h1>
          <p className="text-sm md:text-base text-muted-foreground">
            Complete history of all tool executions
          </p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          {/* Connection Status */}
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-muted/50 text-sm">
            {isWsConnected ? (
              <>
                <Wifi className="w-4 h-4 text-green-500" />
                <span className="text-muted-foreground">Live</span>
              </>
            ) : isPolling ? (
              <>
                <RefreshCw className="w-4 h-4 text-yellow-500" />
                <span className="text-muted-foreground">Polling</span>
              </>
            ) : (
              <>
                <WifiOff className="w-4 h-4 text-red-500" />
                <span className="text-muted-foreground">Offline</span>
              </>
            )}
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={handleRefresh}
            className="w-full md:w-auto"
          >
            <RefreshCw className="w-4 h-4 mr-2" />
            Refresh
          </Button>
          <Button
            variant="outline"
            onClick={() => setShowExport(!showExport)}
            className="w-full md:w-auto"
          >
            <Download className="w-4 h-4 mr-2" />
            Export
          </Button>
        </div>
      </motion.div>

      {/* New Logs Notification */}
      {newLogsCount > 0 && (
        <motion.div
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          className="bg-primary/10 border border-primary/30 rounded-lg p-3 flex items-center justify-between"
        >
          <span className="text-sm">
            <span className="font-semibold">{newLogsCount}</span> new log{newLogsCount !== 1 ? 's' : ''} available
          </span>
          <Button size="sm" onClick={handleShowNewLogs}>
            Show
          </Button>
        </motion.div>
      )}

      {/* Export Panel */}
      {showExport && (
        <motion.div
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: 'auto' }}
          exit={{ opacity: 0, height: 0 }}
        >
          <Card className="border-primary/50 bg-primary/5">
            <CardContent className="pt-6">
              <div className="flex flex-col sm:flex-row items-start sm:items-center gap-4">
                <div className="flex-1">
                  <h3 className="font-semibold mb-2">Export Audit Logs</h3>
                  <p className="text-sm text-muted-foreground">
                    Export {filtered} logs matching current filters
                  </p>
                </div>
                <div className="flex items-center gap-2 w-full sm:w-auto">
                  <select
                    value={exportFormat}
                    onChange={(e) => setExportFormat(e.target.value as 'json' | 'csv')}
                    className="px-3 py-2 rounded-lg border border-input bg-background text-sm flex-1 sm:flex-none"
                  >
                    <option value="json">JSON</option>
                    <option value="csv">CSV</option>
                  </select>
                  <Button onClick={handleExport} disabled={isExporting}>
                    {isExporting ? 'Exporting...' : 'Download'}
                  </Button>
                  <Button variant="ghost" size="icon" onClick={() => setShowExport(false)}>
                    <X className="w-4 h-4" />
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>
        </motion.div>
      )}

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard
          label="Total Logs"
          value={total}
          icon={FileText}
          delay={0}
        />
        <StatCard
          label="Showing"
          value={logs.length}
          icon={FileText}
          variant="default"
          delay={0.1}
        />
        <StatCard
          label="Page"
          value={`${page + 1} / ${totalPages || 1}`}
          icon={FileText}
          variant="default"
          delay={0.2}
        />
        <StatCard
          label="Filtered"
          value={filtered}
          icon={FileText}
          variant="default"
          delay={0.3}
        />
      </div>

      {/* Filters */}
      <Card>
        <CardContent className="pt-6">
          <div className="flex flex-col md:flex-row gap-4">
            <div className="flex-1 relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <Input
                placeholder="Search by tool name, category, or error message..."
                value={searchTerm}
                onChange={(e) => {
                  setSearchTerm(e.target.value)
                  setPage(0) // Reset to first page on search
                }}
                className="pl-10"
              />
            </div>
            <div className="flex flex-wrap gap-2">
              <select
                value={statusFilter}
                onChange={(e) => {
                  setStatusFilter(e.target.value)
                  setPage(0)
                }}
                className="px-3 py-2 rounded-lg border border-input bg-background text-sm focus:outline-none focus:ring-2 focus:ring-ring"
              >
                <option value="all">All Status</option>
                <option value="success">Success</option>
                <option value="error">Error</option>
                <option value="blocked">Blocked</option>
                <option value="hitl_approved">HITL Approved</option>
                <option value="hitl_rejected">HITL Rejected</option>
              </select>
              <select
                value={categoryFilter}
                onChange={(e) => {
                  setCategoryFilter(e.target.value)
                  setPage(0)
                }}
                className="px-3 py-2 rounded-lg border border-input bg-background text-sm focus:outline-none focus:ring-2 focus:ring-ring"
              >
                <option value="all">All Categories</option>
                {categories.map((cat) => (
                  <option key={cat} value={cat}>{cat}</option>
                ))}
              </select>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Log Table */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle>Execution History</CardTitle>
            <Badge variant="default">{filtered} logs</Badge>
          </div>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="flex items-center justify-center py-12">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
            </div>
          ) : logs.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground">
              <Search className="w-12 h-12 mx-auto mb-3 opacity-50" />
              <p>No logs found matching your filters</p>
            </div>
          ) : (
            <div className="overflow-x-auto -mx-4 md:mx-0">
              <div className="inline-block min-w-full align-middle">
                <table className="w-full">
                  <thead>
                    <tr className="border-b border-border">
                      <th className="text-left py-3 px-3 md:px-4 text-xs md:text-sm font-semibold text-muted-foreground">
                        Timestamp
                      </th>
                      <th className="text-left py-3 px-3 md:px-4 text-xs md:text-sm font-semibold text-muted-foreground">
                        Tool
                      </th>
                      <th className="text-left py-3 px-3 md:px-4 text-xs md:text-sm font-semibold text-muted-foreground hidden sm:table-cell">
                        Protocol
                      </th>
                      <th className="text-left py-3 px-3 md:px-4 text-xs md:text-sm font-semibold text-muted-foreground">
                        Status
                      </th>
                      <th className="text-left py-3 px-3 md:px-4 text-xs md:text-sm font-semibold text-muted-foreground hidden md:table-cell">
                        Duration
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {logs.map((log, index) => (
                      <motion.tr
                        key={log.id}
                        initial={{ opacity: 0, y: 10 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: Math.min(index * 0.02, 0.5) }}
                        className="border-b border-border/50 hover:bg-accent/50 transition-colors"
                      >
                        <td className="py-3 px-3 md:px-4 text-xs md:text-sm">
                          <div className="hidden md:block">{formatTimestamp(log.timestamp)}</div>
                          <div className="md:hidden text-xs">{new Date(log.timestamp).toLocaleTimeString()}</div>
                        </td>
                        <td className="py-3 px-3 md:px-4">
                          <code className="text-xs md:text-sm font-mono break-all">
                            {log.tool_category}_{log.tool_name}
                          </code>
                        </td>
                        <td className="py-3 px-3 md:px-4 text-xs md:text-sm uppercase hidden sm:table-cell">
                          {log.protocol}
                        </td>
                        <td className="py-3 px-3 md:px-4">
                          <Badge className={getStatusBadgeClass(log.status)}>
                            {log.status}
                          </Badge>
                        </td>
                        <td className="py-3 px-3 md:px-4 text-xs md:text-sm hidden md:table-cell">
                          {log.duration_ms ? formatDuration(log.duration_ms) : '-'}
                        </td>
                      </motion.tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between mt-4 pt-4 border-t border-border">
              <p className="text-sm text-muted-foreground">
                Showing {page * pageSize + 1} - {Math.min((page + 1) * pageSize, total)} of {total}
              </p>
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setPage((p) => Math.max(0, p - 1))}
                  disabled={page === 0}
                >
                  <ChevronLeft className="w-4 h-4" />
                </Button>
                <span className="text-sm">
                  Page {page + 1} of {totalPages}
                </span>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
                  disabled={page >= totalPages - 1}
                >
                  <ChevronRight className="w-4 h-4" />
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

function StatCard({
  label,
  value,
  icon: Icon,
  variant = 'default',
  delay = 0,
}: {
  label: string
  value: number | string
  icon: any
  variant?: 'default' | 'success' | 'error' | 'warning'
  delay?: number
}) {
  const variantClasses = {
    default: 'text-primary',
    success: 'text-green-500',
    error: 'text-red-500',
    warning: 'text-yellow-500',
  }

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.9 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ delay }}
    >
      <Card hover>
        <CardContent className="pt-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-muted-foreground mb-1">{label}</p>
              <p className={`text-xl md:text-3xl font-bold ${variantClasses[variant]}`}>
                {value}
              </p>
            </div>
            <Icon className={`w-6 h-6 md:w-8 md:h-8 ${variantClasses[variant]} opacity-50`} />
          </div>
        </CardContent>
      </Card>
    </motion.div>
  )
}
