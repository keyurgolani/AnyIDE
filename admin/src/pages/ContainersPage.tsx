import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Container, Search, RefreshCw, AlertCircle, ChevronRight,
  Play, Square, Clock, Server, FileText
} from 'lucide-react'
import { api, ContainerInfo } from '@/lib/api'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { cn } from '@/lib/utils'

export default function ContainersPage() {
  const [searchTerm, setSearchTerm] = useState('')
  const [selectedContainer, setSelectedContainer] = useState<ContainerInfo | null>(null)
  const [logsTail, setLogsTail] = useState(100)

  // Fetch containers
  const {
    data: containers,
    isLoading,
    error,
    refetch,
  } = useQuery({
    queryKey: ['containers'],
    queryFn: () => api.getContainers(),
    refetchInterval: 30000, // Refresh every 30 seconds
  })

  // Fetch logs for selected container
  const {
    data: logsData,
    isLoading: isLoadingLogs,
    refetch: refetchLogs,
  } = useQuery({
    queryKey: ['container-logs', selectedContainer?.id, logsTail],
    queryFn: () => {
      if (!selectedContainer) return null
      return api.getContainerLogs(selectedContainer.id, logsTail)
    },
    enabled: !!selectedContainer,
    refetchInterval: false,
  })

  // Filter containers
  const filteredContainers = (containers || []).filter((container) => {
    if (!searchTerm) return true
    const term = searchTerm.toLowerCase()
    return (
      container.name.toLowerCase().includes(term) ||
      container.image.toLowerCase().includes(term) ||
      container.status.toLowerCase().includes(term)
    )
  })

  const getStatusColor = (status: string) => {
    const s = status.toLowerCase()
    if (s.includes('running')) return 'success'
    if (s.includes('exited') || s.includes('stopped')) return 'error'
    if (s.includes('paused')) return 'warning'
    return 'default'
  }

  return (
    <div className="space-y-4 md:space-y-6">
      {/* Page Header */}
      <motion.div
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex flex-col md:flex-row md:items-center md:justify-between gap-4"
      >
        <div>
          <h1 className="text-3xl md:text-4xl font-bold gradient-text mb-2">Container Logs</h1>
          <p className="text-sm md:text-base text-muted-foreground">
            Browse Docker containers and view their logs
          </p>
        </div>
        <Button
          variant="outline"
          onClick={() => refetch()}
          className="w-full md:w-auto"
        >
          <RefreshCw className="w-4 h-4 mr-2" />
          Refresh
        </Button>
      </motion.div>

      {/* Error State */}
      {error && (
        <Card className="border-destructive/50 bg-destructive/5">
          <CardContent className="pt-6">
            <div className="flex items-center gap-3">
              <AlertCircle className="w-5 h-5 text-destructive" />
              <div>
                <p className="font-semibold">Failed to load containers</p>
                <p className="text-sm text-muted-foreground">
                  {(error as Error).message || 'Docker may not be available on this system'}
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Stats */}
      {!error && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatCard
            icon={Container}
            label="Total Containers"
            value={containers?.length || 0}
            delay={0}
          />
          <StatCard
            icon={Play}
            label="Running"
            value={containers?.filter(c => c.status.toLowerCase().includes('running')).length || 0}
            variant="success"
            delay={0.1}
          />
          <StatCard
            icon={Square}
            label="Stopped"
            value={containers?.filter(c => c.status.toLowerCase().includes('exited') || c.status.toLowerCase().includes('stopped')).length || 0}
            variant="error"
            delay={0.2}
          />
          <StatCard
            icon={Clock}
            label="Other"
            value={containers?.filter(c => {
              const s = c.status.toLowerCase()
              return !s.includes('running') && !s.includes('exited') && !s.includes('stopped')
            }).length || 0}
            variant="warning"
            delay={0.3}
          />
        </div>
      )}

      {/* Main Content */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Container List */}
        <div className="lg:col-span-1">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Server className="w-5 h-5" />
                Containers
              </CardTitle>
              <CardDescription>
                Select a container to view logs
              </CardDescription>
              <div className="mt-2 relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                <Input
                  placeholder="Search containers..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="pl-10"
                />
              </div>
            </CardHeader>
            <CardContent>
              {isLoading ? (
                <div className="flex items-center justify-center py-8">
                  <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-primary"></div>
                </div>
              ) : filteredContainers.length === 0 ? (
                <div className="text-center py-8 text-muted-foreground">
                  <Container className="w-10 h-10 mx-auto mb-2 opacity-50" />
                  <p>No containers found</p>
                </div>
              ) : (
                <div className="space-y-2 max-h-[500px] overflow-y-auto">
                  {filteredContainers.map((container) => (
                    <button
                      key={container.id}
                      onClick={() => setSelectedContainer(container)}
                      className={cn(
                        'w-full flex items-center justify-between p-3 rounded-lg transition-all text-left',
                        selectedContainer?.id === container.id
                          ? 'bg-primary/10 border border-primary/50 ring-1 ring-primary'
                          : 'bg-accent/30 hover:bg-accent/50 border border-transparent'
                      )}
                    >
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <code className="text-sm font-mono truncate">{container.name}</code>
                          <Badge variant={getStatusColor(container.status) as any} className="text-xs">
                            {container.status.split(' ')[0]}
                          </Badge>
                        </div>
                        <p className="text-xs text-muted-foreground truncate mt-1">
                          {container.image}
                        </p>
                      </div>
                      <ChevronRight className="w-4 h-4 text-muted-foreground flex-shrink-0" />
                    </button>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Log Viewer */}
        <div className="lg:col-span-2">
          <Card className="h-full">
            <CardHeader>
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle className="flex items-center gap-2">
                    <FileText className="w-5 h-5" />
                    {selectedContainer ? `Logs: ${selectedContainer.name}` : 'Container Logs'}
                  </CardTitle>
                  <CardDescription>
                    {selectedContainer
                      ? `Last ${logsTail} log entries`
                      : 'Select a container to view logs'}
                  </CardDescription>
                </div>
                {selectedContainer && (
                  <div className="flex items-center gap-2">
                    <select
                      value={logsTail}
                      onChange={(e) => setLogsTail(Number(e.target.value))}
                      className="px-3 py-1.5 rounded-lg border border-input bg-background text-sm"
                    >
                      <option value={50}>Last 50</option>
                      <option value={100}>Last 100</option>
                      <option value={200}>Last 200</option>
                      <option value={500}>Last 500</option>
                      <option value={1000}>Last 1000</option>
                    </select>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => refetchLogs()}
                    >
                      <RefreshCw className="w-4 h-4" />
                    </Button>
                  </div>
                )}
              </div>
            </CardHeader>
            <CardContent>
              <AnimatePresence mode="wait">
                {selectedContainer ? (
                  <motion.div
                    key={selectedContainer.id}
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    className="h-[500px] overflow-hidden"
                  >
                    {isLoadingLogs ? (
                      <div className="flex items-center justify-center h-full">
                        <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-primary"></div>
                      </div>
                    ) : (
                      <div className="h-full overflow-auto bg-muted/30 rounded-lg p-4 font-mono text-xs">
                        <pre className="whitespace-pre-wrap break-words">
                          {logsData?.logs || 'No logs available'}
                        </pre>
                      </div>
                    )}
                  </motion.div>
                ) : (
                  <motion.div
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    className="h-[500px] flex flex-col items-center justify-center text-muted-foreground"
                  >
                    <FileText className="w-12 h-12 mb-3 opacity-50" />
                    <p>No container selected</p>
                    <p className="text-sm mt-1">Select a container from the list to view its logs</p>
                  </motion.div>
                )}
              </AnimatePresence>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}

function StatCard({
  icon: Icon,
  label,
  value,
  variant = 'default',
  delay = 0,
}: {
  icon: any
  label: string
  value: number
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
              <p className={`text-2xl font-bold ${variantClasses[variant]}`}>
                {value}
              </p>
            </div>
            <Icon className={`w-6 h-6 ${variantClasses[variant]} opacity-50`} />
          </div>
        </CardContent>
      </Card>
    </motion.div>
  )
}
