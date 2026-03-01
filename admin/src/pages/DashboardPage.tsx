import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { motion, AnimatePresence } from 'framer-motion'
import { 
  Bell, Activity, FileText, Clock, CheckCircle, XCircle, 
  AlertTriangle, TrendingUp, ChevronDown, ChevronUp, ExternalLink
} from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { api, HITLRequest } from '@/lib/api'
import { wsClient } from '@/lib/websocket'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { formatRelativeTime, formatDuration, getStatusBadgeClass } from '@/lib/utils'

export default function DashboardPage() {
  const navigate = useNavigate()
  const [expandedSections, setExpandedSections] = useState({
    hitl: true,
    health: true,
    audit: true,
  })

  const toggleSection = (section: keyof typeof expandedSections) => {
    setExpandedSections(prev => ({ ...prev, [section]: !prev[section] }))
  }

  return (
    <div className="space-y-4 md:space-y-6">
      {/* Page Header */}
      <motion.div
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
      >
        <h1 className="text-3xl md:text-4xl font-bold gradient-text mb-2">Dashboard</h1>
        <p className="text-sm md:text-base text-muted-foreground">
          Monitor and manage your AnyIDE system
        </p>
      </motion.div>

      {/* HITL Queue Widget */}
      <HITLWidget 
        expanded={expandedSections.hitl} 
        onToggle={() => toggleSection('hitl')}
        onViewAll={() => navigate('/hitl')}
      />

      {/* System Health Widget */}
      <SystemHealthWidget 
        expanded={expandedSections.health} 
        onToggle={() => toggleSection('health')}
        onViewAll={() => navigate('/health')}
      />

      {/* Recent Audit Logs Widget */}
      <AuditLogWidget 
        expanded={expandedSections.audit} 
        onToggle={() => toggleSection('audit')}
        onViewAll={() => navigate('/audit')}
      />
    </div>
  )
}

function HITLWidget({ expanded, onToggle, onViewAll }: { 
  expanded: boolean
  onToggle: () => void
  onViewAll: () => void
}) {
  const [requests, setRequests] = useState<HITLRequest[]>([])

  useEffect(() => {
    if (!wsClient.isConnected()) {
      wsClient.connect()
    }

    wsClient.requestPendingRequests()

    const unsubscribe = wsClient.onMessage((message) => {
      if (message.type === 'pending_requests') {
        setRequests(message.data)
      } else if (message.type === 'hitl_request') {
        setRequests((prev) => {
          const exists = prev.some(req => req.id === message.data.id)
          if (exists) return prev
          return [message.data, ...prev]
        })
      } else if (message.type === 'hitl_update') {
        setRequests((prev) =>
          prev.filter((req) => req.id !== message.data.id || message.data.status === 'pending')
        )
      }
    })

    return () => {
      unsubscribe()
    }
  }, [])

  const handleApprove = (id: string) => {
    wsClient.approveRequest(id)
  }

  const handleReject = (id: string) => {
    wsClient.rejectRequest(id, 'Rejected by administrator')
  }

  const pendingRequests = requests.filter((r) => r.status === 'pending')

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.1 }}
    >
      <Card glow={pendingRequests.length > 0} className={pendingRequests.length > 0 ? 'glow-yellow' : ''}>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Bell className={`w-6 h-6 ${pendingRequests.length > 0 ? 'text-yellow-500' : 'text-muted-foreground'}`} />
              <div>
                <CardTitle className="text-xl">HITL Approval Queue</CardTitle>
                <CardDescription>Pending tool execution requests</CardDescription>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Badge variant={pendingRequests.length > 0 ? 'warning' : 'default'} className="text-lg px-3 py-1">
                {pendingRequests.length}
              </Badge>
              <Button
                variant="ghost"
                size="sm"
                onClick={onToggle}
                className="ml-2"
              >
                {expanded ? <ChevronUp size={20} /> : <ChevronDown size={20} />}
              </Button>
            </div>
          </div>
        </CardHeader>
        
        <AnimatePresence>
          {expanded && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.3 }}
            >
              <CardContent>
                {pendingRequests.length === 0 ? (
                  <div className="text-center py-8">
                    <CheckCircle className="w-12 h-12 mx-auto mb-3 text-green-500 opacity-50" />
                    <p className="text-muted-foreground">No pending requests</p>
                    <p className="text-sm text-muted-foreground mt-1">
                      All tool executions are running smoothly
                    </p>
                  </div>
                ) : (
                  <div className="space-y-3">
                    {pendingRequests.slice(0, 3).map((request, index) => (
                      <CompactHITLCard
                        key={request.id}
                        request={request}
                        index={index}
                        onApprove={() => handleApprove(request.id)}
                        onReject={() => handleReject(request.id)}
                      />
                    ))}
                    {pendingRequests.length > 3 && (
                      <Button
                        variant="outline"
                        className="w-full"
                        onClick={onViewAll}
                      >
                        View All {pendingRequests.length} Requests
                        <ExternalLink className="w-4 h-4 ml-2" />
                      </Button>
                    )}
                  </div>
                )}
              </CardContent>
            </motion.div>
          )}
        </AnimatePresence>
      </Card>
    </motion.div>
  )
}

function CompactHITLCard({
  request,
  index,
  onApprove,
  onReject,
}: {
  request: HITLRequest
  index: number
  onApprove: () => void
  onReject: () => void
}) {
  const [timeLeft, setTimeLeft] = useState(0)

  useEffect(() => {
    const updateTimeLeft = () => {
      const created = new Date(request.created_at).getTime()
      const now = Date.now()
      const elapsed = (now - created) / 1000
      const remaining = Math.max(0, request.ttl_seconds - elapsed)
      setTimeLeft(remaining)
    }

    updateTimeLeft()
    const interval = setInterval(updateTimeLeft, 1000)
    return () => clearInterval(interval)
  }, [request])

  const progress = (timeLeft / request.ttl_seconds) * 100

  return (
    <motion.div
      initial={{ opacity: 0, x: -20 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: index * 0.05 }}
      className="glass rounded-lg p-3 md:p-4"
    >
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-2">
        <div className="flex-1 min-w-0">
          <h4 className="font-semibold text-sm md:text-base truncate">
            {request.tool_category}_{request.tool_name}
          </h4>
          <p className="text-xs text-muted-foreground">
            {formatRelativeTime(request.created_at)}
          </p>
        </div>
        <Badge variant="warning" className="w-fit">
          <Clock className="w-3 h-3 mr-1" />
          {Math.floor(timeLeft)}s
        </Badge>
      </div>

      <div className="mb-3">
        <div className="h-1.5 bg-muted rounded-full overflow-hidden">
          <motion.div
            className="h-full bg-gradient-to-r from-yellow-500 to-orange-500"
            initial={{ width: '100%' }}
            animate={{ width: `${progress}%` }}
            transition={{ duration: 1 }}
          />
        </div>
      </div>

      <div className="flex gap-2">
        <Button
          size="sm"
          onClick={onApprove}
          className="flex-1"
        >
          <CheckCircle className="w-4 h-4 mr-1" />
          Approve
        </Button>
        <Button
          size="sm"
          variant="destructive"
          onClick={onReject}
          className="flex-1"
        >
          <XCircle className="w-4 h-4 mr-1" />
          Reject
        </Button>
      </div>
    </motion.div>
  )
}

function SystemHealthWidget({ expanded, onToggle, onViewAll }: { 
  expanded: boolean
  onToggle: () => void
  onViewAll: () => void
}) {
  const { data: health } = useQuery({
    queryKey: ['system-health'],
    queryFn: () => api.getSystemHealth(),
    refetchInterval: 5000,
  })

  const uptime = health?.uptime || 0
  const pendingHitl = health?.pending_hitl || 0
  const toolsExecuted = health?.tools_executed || 0
  const errorRate = health?.error_rate || 0

  const isHealthy = errorRate < 0.1 && pendingHitl < 10

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.2 }}
    >
      <Card glow={isHealthy} className={isHealthy ? 'glow-green' : 'glow-red'}>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              {isHealthy ? (
                <CheckCircle className="w-6 h-6 text-green-500" />
              ) : (
                <AlertTriangle className="w-6 h-6 text-red-500" />
              )}
              <div>
                <CardTitle className="text-xl">System Health</CardTitle>
                <CardDescription>
                  {isHealthy ? 'All systems operational' : 'Attention required'}
                </CardDescription>
              </div>
            </div>
            <Button
              variant="ghost"
              size="sm"
              onClick={onToggle}
            >
              {expanded ? <ChevronUp size={20} /> : <ChevronDown size={20} />}
            </Button>
          </div>
        </CardHeader>
        
        <AnimatePresence>
          {expanded && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.3 }}
            >
              <CardContent>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
                  <MetricCard
                    label="Uptime"
                    value={`${Math.floor(uptime / 3600)}h ${Math.floor((uptime % 3600) / 60)}m`}
                    icon={Clock}
                    variant="default"
                  />
                  <MetricCard
                    label="Pending HITL"
                    value={pendingHitl.toString()}
                    icon={AlertTriangle}
                    variant={pendingHitl > 5 ? 'warning' : 'success'}
                  />
                  <MetricCard
                    label="Tools Executed"
                    value={toolsExecuted.toString()}
                    icon={TrendingUp}
                    variant="default"
                  />
                  <MetricCard
                    label="Error Rate"
                    value={`${(errorRate * 100).toFixed(1)}%`}
                    icon={Activity}
                    variant={errorRate > 0.1 ? 'error' : 'success'}
                  />
                </div>
                
                <Button
                  variant="outline"
                  className="w-full"
                  onClick={onViewAll}
                >
                  View Detailed Health Metrics
                  <ExternalLink className="w-4 h-4 ml-2" />
                </Button>
              </CardContent>
            </motion.div>
          )}
        </AnimatePresence>
      </Card>
    </motion.div>
  )
}

function MetricCard({
  label,
  value,
  icon: Icon,
  variant = 'default',
}: {
  label: string
  value: string
  icon: any
  variant?: 'default' | 'success' | 'error' | 'warning'
}) {
  const variantClasses = {
    default: 'text-primary',
    success: 'text-green-500',
    error: 'text-red-500',
    warning: 'text-yellow-500',
  }

  return (
    <div className="glass rounded-lg p-3">
      <div className="flex items-center justify-between mb-1">
        <p className="text-xs text-muted-foreground">{label}</p>
        <Icon className={`w-4 h-4 ${variantClasses[variant]} opacity-50`} />
      </div>
      <p className={`text-xl font-bold ${variantClasses[variant]}`}>
        {value}
      </p>
    </div>
  )
}

function AuditLogWidget({ expanded, onToggle, onViewAll }: { 
  expanded: boolean
  onToggle: () => void
  onViewAll: () => void
}) {
  const { data: logs = [] } = useQuery({
    queryKey: ['audit-logs'],
    queryFn: () => api.getAuditLogs(10),
    refetchInterval: 5000,
  })

  const statusCounts = logs.reduce((acc, log) => {
    acc[log.status] = (acc[log.status] || 0) + 1
    return acc
  }, {} as Record<string, number>)

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.3 }}
    >
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <FileText className="w-6 h-6 text-muted-foreground" />
              <div>
                <CardTitle className="text-xl">Recent Activity</CardTitle>
                <CardDescription>Latest tool executions</CardDescription>
              </div>
            </div>
            <Button
              variant="ghost"
              size="sm"
              onClick={onToggle}
            >
              {expanded ? <ChevronUp size={20} /> : <ChevronDown size={20} />}
            </Button>
          </div>
        </CardHeader>
        
        <AnimatePresence>
          {expanded && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.3 }}
            >
              <CardContent>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
                  <StatBadge label="Success" value={statusCounts.success || 0} variant="success" />
                  <StatBadge label="Errors" value={statusCounts.error || 0} variant="error" />
                  <StatBadge label="Blocked" value={statusCounts.blocked || 0} variant="warning" />
                  <StatBadge label="Total" value={logs.length} variant="default" />
                </div>

                {logs.length === 0 ? (
                  <div className="text-center py-8 text-muted-foreground">
                    No recent activity
                  </div>
                ) : (
                  <div className="space-y-2">
                    {logs.slice(0, 5).map((log, index) => (
                      <motion.div
                        key={log.id}
                        initial={{ opacity: 0, x: -20 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ delay: index * 0.05 }}
                        className="flex items-center justify-between p-2 rounded-lg hover:bg-accent/50 transition-colors"
                      >
                        <div className="flex-1 min-w-0">
                          <code className="text-xs md:text-sm font-mono truncate block">
                            {log.tool_category}_{log.tool_name}
                          </code>
                          <p className="text-xs text-muted-foreground">
                            {formatRelativeTime(log.timestamp)}
                          </p>
                        </div>
                        <div className="flex items-center gap-2">
                          {log.duration_ms && (
                            <span className="text-xs text-muted-foreground hidden md:inline">
                              {formatDuration(log.duration_ms)}
                            </span>
                          )}
                          <Badge className={getStatusBadgeClass(log.status)}>
                            {log.status}
                          </Badge>
                        </div>
                      </motion.div>
                    ))}
                  </div>
                )}

                <Button
                  variant="outline"
                  className="w-full mt-4"
                  onClick={onViewAll}
                >
                  View Full Audit Log
                  <ExternalLink className="w-4 h-4 ml-2" />
                </Button>
              </CardContent>
            </motion.div>
          )}
        </AnimatePresence>
      </Card>
    </motion.div>
  )
}

function StatBadge({ 
  label, 
  value, 
  variant 
}: { 
  label: string
  value: number
  variant: 'default' | 'success' | 'error' | 'warning'
}) {
  const variantClasses = {
    default: 'bg-accent text-foreground',
    success: 'bg-green-500/10 text-green-500',
    error: 'bg-red-500/10 text-red-500',
    warning: 'bg-yellow-500/10 text-yellow-500',
  }

  return (
    <div className={`rounded-lg p-2 ${variantClasses[variant]}`}>
      <p className="text-xs opacity-75">{label}</p>
      <p className="text-xl font-bold">{value}</p>
    </div>
  )
}
