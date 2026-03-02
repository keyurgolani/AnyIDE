import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import {
  Settings, Shield, Database, Folder, Globe, Wrench,
  CheckCircle, AlertCircle, RefreshCw, Bot, Zap
} from 'lucide-react'
import { api } from '@/lib/api'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'

export default function ConfigPage() {
  const [llmTestResults, setLlmTestResults] = useState<Record<string, any>>({})

  const { data: config, isLoading, refetch } = useQuery({
    queryKey: ['config'],
    queryFn: () => api.getConfig(),
  })

  const llmTestMutation = useMutation({
    mutationFn: (endpointId: string) => api.testLLMEndpoint(endpointId),
    onSuccess: (result) => {
      setLlmTestResults((prev) => ({ ...prev, [result.endpoint_id]: result }))
    },
  })

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[50vh]">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary"></div>
      </div>
    )
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
          <h1 className="text-3xl md:text-4xl font-bold gradient-text mb-2">Configuration</h1>
          <p className="text-sm md:text-base text-muted-foreground">
            View current system configuration and settings
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

      {/* Status Overview */}
      <motion.div
        initial={{ opacity: 0, scale: 0.9 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ delay: 0.1 }}
      >
        <Card>
          <CardContent className="pt-6">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <StatusItem
                icon={Shield}
                label="Authentication"
                value={config?.auth_enabled ? 'Enabled' : 'Disabled'}
                status={config?.auth_enabled ? 'success' : 'warning'}
              />
              <StatusItem
                icon={Database}
                label="Database"
                value="Connected"
                status="success"
              />
              <StatusItem
                icon={Folder}
                label="Workspace"
                value="Active"
                status="success"
              />
              <StatusItem
                icon={Shield}
                label="Policy Rules"
                value={config?.policy_rules_count || 0}
                status="success"
              />
            </div>
          </CardContent>
        </Card>
      </motion.div>

      {/* Configuration Details */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* General Settings */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
        >
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Settings className="w-5 h-5" />
                General Settings
              </CardTitle>
              <CardDescription>Core system configuration</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                <ConfigRow label="Log Level" value={config?.log_level || 'INFO'} />
                <ConfigRow label="Workspace Path" value={config?.workspace_path || '/workspace'} monospace />
                <ConfigRow label="Database Path" value={config?.database_path || '/app/data/hostbridge.db'} monospace />
                <ConfigRow
                  label="Authentication"
                  value={config?.auth_enabled ? 'Enabled' : 'Disabled'}
                  badge
                  badgeVariant={config?.auth_enabled ? 'success' : 'warning'}
                />
              </div>
            </CardContent>
          </Card>
        </motion.div>

        {/* HTTP Configuration */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3 }}
        >
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Globe className="w-5 h-5" />
                HTTP Configuration
              </CardTitle>
              <CardDescription>HTTP client security settings</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                <ConfigRow
                  label="Block Private IPs"
                  value={config?.http_config?.block_private_ips ? 'Yes' : 'No'}
                  badge
                  badgeVariant={config?.http_config?.block_private_ips ? 'success' : 'warning'}
                />
                <ConfigRow
                  label="Block Metadata Endpoints"
                  value={config?.http_config?.block_metadata_endpoints ? 'Yes' : 'No'}
                  badge
                  badgeVariant={config?.http_config?.block_metadata_endpoints ? 'success' : 'warning'}
                />
                <ConfigRow label="Timeout (seconds)" value={config?.http_config?.timeout_seconds?.toString() || '30'} />
                <ConfigRow
                  label="Allowed Domains"
                  value={config?.http_config?.allow_domains?.length || 0}
                  suffix={config?.http_config?.allow_domains?.length === 0 ? ' (all allowed)' : ' domains'}
                />
                <ConfigRow
                  label="Blocked Domains"
                  value={config?.http_config?.block_domains?.length || 0}
                  suffix={config?.http_config?.block_domains?.length === 0 ? ' (none blocked)' : ' domains'}
                />
              </div>
            </CardContent>
          </Card>
        </motion.div>

        {/* Tool Configurations */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.4 }}
        >
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Bot className="w-5 h-5" />
                LLM Endpoints
              </CardTitle>
              <CardDescription>
                System-level LLM capability configured via `config.yaml` and tested from admin
              </CardDescription>
            </CardHeader>
            <CardContent>
              {(config?.llm_endpoints || []).length === 0 ? (
                <p className="text-sm text-muted-foreground">No LLM endpoints configured.</p>
              ) : (
                <div className="space-y-3">
                  {(config?.llm_endpoints || []).map((endpoint: any) => {
                    const result = llmTestResults[endpoint.id]
                    return (
                      <div
                        key={endpoint.id}
                        className="p-4 rounded-lg bg-accent/30 border border-border/50 space-y-2"
                      >
                        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-2">
                          <div>
                            <p className="font-medium">{endpoint.id}</p>
                            <p className="text-xs text-muted-foreground">
                              {endpoint.provider} · {endpoint.default_model}
                            </p>
                          </div>
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => llmTestMutation.mutate(endpoint.id)}
                            disabled={llmTestMutation.isPending}
                          >
                            <Zap className="w-4 h-4 mr-2" />
                            Test Endpoint
                          </Button>
                        </div>
                        <p className="text-xs font-mono text-muted-foreground break-all">{endpoint.base_url}</p>
                        {result && (
                          <div className="text-xs">
                            <Badge variant={result.success ? 'success' : 'error'}>
                              {result.success ? 'Reachable' : 'Failed'}
                            </Badge>
                            {result.success && (
                              <span className="ml-2 text-muted-foreground">
                                {result.latency_ms} ms · {result.model}
                              </span>
                            )}
                            {!result.success && result.error_message && (
                              <p className="mt-2 text-red-400">{result.error_message}</p>
                            )}
                          </div>
                        )}
                      </div>
                    )
                  })}
                </div>
              )}
            </CardContent>
          </Card>
        </motion.div>

        {/* Tool Configurations */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.45 }}
          className="lg:col-span-2"
        >
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Wrench className="w-5 h-5" />
                Tool Configurations
              </CardTitle>
              <CardDescription>Per-tool settings and policies</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
                {Object.entries(config?.tool_configs || {}).map(([toolName, toolConfig]: [string, any]) => (
                  <motion.div
                    key={toolName}
                    initial={{ opacity: 0, scale: 0.9 }}
                    animate={{ opacity: 1, scale: 1 }}
                    className="p-4 rounded-lg bg-accent/30 border border-border/50"
                  >
                    <div className="flex items-center justify-between mb-2">
                      <span className="font-medium capitalize">{toolName}</span>
                      <Badge variant={toolConfig.enabled !== false ? 'success' : 'warning'}>
                        {toolConfig.enabled !== false ? 'Enabled' : 'Disabled'}
                      </Badge>
                    </div>
                    {toolConfig.policy && (
                      <p className="text-xs text-muted-foreground">
                        Policy: <code className="font-mono">{toolConfig.policy}</code>
                      </p>
                    )}
                  </motion.div>
                ))}
              </div>
            </CardContent>
          </Card>
        </motion.div>
      </div>

      {/* Security Notes */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.5 }}
      >
        <Card className="border-yellow-500/50 bg-yellow-500/5">
          <CardContent className="pt-6">
            <div className="flex items-start gap-3">
              <AlertCircle className="w-5 h-5 text-yellow-500 flex-shrink-0 mt-0.5" />
              <div>
                <h4 className="font-semibold text-yellow-500">Security Note</h4>
                <p className="text-sm text-muted-foreground mt-1">
                  This view displays sanitized configuration data. Sensitive values like passwords and API keys
                  are never exposed through the admin interface. Use the secrets management system to manage
                  sensitive configuration values.
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      </motion.div>
    </div>
  )
}

function StatusItem({
  icon: Icon,
  label,
  value,
  status,
}: {
  icon: any
  label: string
  value: string | number
  status: 'success' | 'warning' | 'error'
}) {
  const statusColors = {
    success: 'text-green-500',
    warning: 'text-yellow-500',
    error: 'text-red-500',
  }

  const StatusIcon = status === 'success' ? CheckCircle : AlertCircle

  return (
    <div className="flex items-center gap-3 p-3 rounded-lg bg-accent/30">
      <Icon className="w-5 h-5 text-muted-foreground" />
      <div>
        <p className="text-xs text-muted-foreground">{label}</p>
        <div className="flex items-center gap-1">
          <StatusIcon className={`w-3 h-3 ${statusColors[status]}`} />
          <span className={`font-medium ${statusColors[status]}`}>{value}</span>
        </div>
      </div>
    </div>
  )
}

function ConfigRow({
  label,
  value,
  suffix,
  monospace,
  badge,
  badgeVariant,
}: {
  label: string
  value: string | number
  suffix?: string
  monospace?: boolean
  badge?: boolean
  badgeVariant?: 'default' | 'success' | 'warning' | 'error'
}) {
  return (
    <div className="flex items-center justify-between py-2 border-b border-border/30 last:border-0">
      <span className="text-sm text-muted-foreground">{label}</span>
      {badge ? (
        <Badge variant={badgeVariant || 'default'}>{value}{suffix}</Badge>
      ) : (
        <span className={`text-sm font-medium ${monospace ? 'font-mono' : ''}`}>
          {value}{suffix}
        </span>
      )}
    </div>
  )
}
