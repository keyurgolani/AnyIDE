import { Outlet, NavLink, useLocation } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { Bell, Activity, FileText, LogOut, Menu, X, AlertCircle, CheckCircle, LayoutDashboard, Wrench, Settings, Key, Container } from 'lucide-react'
import { useState, useEffect, useCallback } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useAuthStore } from '@/store/authStore'
import { AuroraBackground } from '../effects/AuroraBackground'
import { FloatingParticles } from '../effects/FloatingParticles'
import { Badge } from '../ui/Badge'
import { api } from '@/lib/api'
import { wsClient } from '@/lib/websocket'
import { cn } from '@/lib/utils'

export default function DashboardLayout() {
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
  const [pendingCount, setPendingCount] = useState(0)
  const logout = useAuthStore((state) => state.logout)
  const location = useLocation()

  const { data: health } = useQuery({
    queryKey: ['system-health'],
    queryFn: () => api.getSystemHealth(),
    refetchInterval: 10000,
  })

  // Request notification permission on mount
  const requestNotificationPermission = useCallback(async () => {
    if ('Notification' in window && Notification.permission === 'default') {
      await Notification.requestPermission()
    }
  }, [])

  // Send browser notification for new HITL requests
  const sendHITLNotification = useCallback((count: number) => {
    if ('Notification' in window && Notification.permission === 'granted') {
      new Notification('AnyIDE - HITL Request', {
        body: `You have ${count} pending approval request${count > 1 ? 's' : ''}`,
        icon: '/admin/favicon.ico',
        tag: 'hitl-request',
        requireInteraction: true,
      })
    }
  }, [])

  useEffect(() => {
    requestNotificationPermission()
  }, [requestNotificationPermission])

  // Listen for HITL updates
  useEffect(() => {
    if (!wsClient.isConnected()) {
      wsClient.connect()
    }

    const unsubscribe = wsClient.onMessage((message) => {
      if (message.type === 'pending_requests') {
        setPendingCount(message.data.length)
      } else if (message.type === 'hitl_request') {
        setPendingCount((prev) => {
          const newCount = prev + 1
          sendHITLNotification(newCount)
          return newCount
        })
      } else if (message.type === 'hitl_update') {
        if (message.data.status !== 'pending') {
          setPendingCount((prev) => Math.max(0, prev - 1))
        }
      }
    })

    return () => {
      unsubscribe()
    }
  }, [sendHITLNotification])

  const navItems = [
    { to: '/', icon: LayoutDashboard, label: 'Dashboard', exact: true },
    { to: '/hitl', icon: Bell, label: 'HITL Queue', badge: pendingCount },
    { to: '/audit', icon: FileText, label: 'Audit Log' },
    { to: '/health', icon: Activity, label: 'System Health' },
    { to: '/tools', icon: Wrench, label: 'Tool Explorer' },
    { to: '/containers', icon: Container, label: 'Containers' },
    { to: '/secrets', icon: Key, label: 'Secrets' },
    { to: '/config', icon: Settings, label: 'Configuration' },
  ]

  const currentPage = navItems.find(item => {
    if (item.exact) {
      return location.pathname === item.to
    }
    return location.pathname.includes(item.to)
  })?.label || 'Dashboard'
  const isHealthy = health && health.error_rate < 0.1 && health.pending_hitl < 10

  return (
    <div className="min-h-screen bg-background text-foreground">
      <AuroraBackground />
      <FloatingParticles />
      
      {/* Header */}
      <motion.header
        initial={{ y: -100 }}
        animate={{ y: 0 }}
        className="fixed top-0 left-0 right-0 z-50 glass border-b border-border/50 backdrop-blur-xl"
      >
        <div className="flex items-center justify-between px-4 md:px-6 py-3 md:py-4">
          <div className="flex items-center gap-3 md:gap-4 flex-1">
            {/* Desktop sidebar toggle */}
            <button
              onClick={() => setSidebarOpen(!sidebarOpen)}
              className="hidden md:block p-2 hover:bg-accent rounded-lg transition-colors"
              aria-label="Toggle sidebar"
            >
              {sidebarOpen ? <X size={24} /> : <Menu size={24} />}
            </button>
            
            {/* Mobile menu toggle */}
            <button
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              className="md:hidden p-2 hover:bg-accent rounded-lg transition-colors"
              aria-label="Toggle mobile menu"
            >
              <Menu size={24} />
            </button>
            
            <div className="flex flex-col">
              <motion.h1
                className="text-xl md:text-2xl font-bold gradient-text"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: 0.2 }}
              >
                AnyIDE Admin
              </motion.h1>
              <span className="text-xs text-muted-foreground hidden md:block">
                {currentPage}
              </span>
            </div>
          </div>
          
          {/* Quick Stats */}
          <div className="hidden lg:flex items-center gap-4 mr-4">
            {health && (
              <>
                <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-accent/50">
                  {isHealthy ? (
                    <CheckCircle className="w-4 h-4 text-green-500" />
                  ) : (
                    <AlertCircle className="w-4 h-4 text-yellow-500" />
                  )}
                  <span className="text-sm font-medium">
                    {isHealthy ? 'Healthy' : 'Warning'}
                  </span>
                </div>
                
                {pendingCount > 0 && (
                  <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-yellow-500/10 text-yellow-500">
                    <Bell className="w-4 h-4" />
                    <span className="text-sm font-semibold">{pendingCount} Pending</span>
                  </div>
                )}
              </>
            )}
          </div>
          
          <motion.button
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
            onClick={logout}
            className="flex items-center gap-2 px-3 md:px-4 py-2 rounded-lg bg-destructive/10 text-destructive hover:bg-destructive/20 transition-colors"
            aria-label="Logout"
          >
            <LogOut size={18} />
            <span className="hidden md:inline">Logout</span>
          </motion.button>
        </div>
      </motion.header>

      {/* Desktop Sidebar */}
      <motion.aside
        initial={{ x: -300 }}
        animate={{ x: sidebarOpen ? 0 : -300 }}
        transition={{ type: 'spring', damping: 20 }}
        className="hidden md:block fixed left-0 top-16 bottom-0 w-64 glass border-r border-border/50 z-40 backdrop-blur-xl"
      >
        <nav className="p-4 space-y-2" role="navigation" aria-label="Main navigation">
          {navItems.map((item, index) => (
            <motion.div
              key={item.to}
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: index * 0.1 }}
            >
              <NavLink
                to={item.to}
                end={item.exact}
                className={({ isActive }) =>
                  cn(
                    'flex items-center justify-between gap-3 px-4 py-3 rounded-lg transition-all duration-200 group',
                    isActive
                      ? 'bg-primary text-primary-foreground shadow-lg glow'
                      : 'hover:bg-accent hover:text-accent-foreground'
                  )
                }
              >
                <div className="flex items-center gap-3">
                  <item.icon size={20} />
                  <span className="font-medium">{item.label}</span>
                </div>
                {item.badge !== undefined && item.badge > 0 && (
                  <Badge variant="warning" className="ml-auto">
                    {item.badge}
                  </Badge>
                )}
              </NavLink>
            </motion.div>
          ))}
        </nav>
        
        {/* Sidebar Footer */}
        <div className="absolute bottom-0 left-0 right-0 p-4 border-t border-border/50">
          <div className="text-xs text-muted-foreground space-y-1">
            <div className="flex justify-between">
              <span>Version</span>
              <span className="font-mono">0.1.0</span>
            </div>
            {health && (
              <div className="flex justify-between">
                <span>Uptime</span>
                <span className="font-mono">
                  {Math.floor(health.uptime / 3600)}h {Math.floor((health.uptime % 3600) / 60)}m
                </span>
              </div>
            )}
          </div>
        </div>
      </motion.aside>

      {/* Mobile Menu Overlay */}
      <AnimatePresence>
        {mobileMenuOpen && (
          <>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setMobileMenuOpen(false)}
              className="md:hidden fixed inset-0 bg-black/50 z-40 backdrop-blur-sm"
            />
            <motion.aside
              initial={{ x: -300 }}
              animate={{ x: 0 }}
              exit={{ x: -300 }}
              transition={{ type: 'spring', damping: 20 }}
              className="md:hidden fixed left-0 top-16 bottom-0 w-64 glass border-r border-border/50 z-50 backdrop-blur-xl"
            >
              <nav className="p-4 space-y-2" role="navigation" aria-label="Mobile navigation">
                {navItems.map((item, index) => (
                  <motion.div
                    key={item.to}
                    initial={{ opacity: 0, x: -20 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: index * 0.1 }}
                  >
                    <NavLink
                      to={item.to}
                      end={item.exact}
                      onClick={() => setMobileMenuOpen(false)}
                      className={({ isActive }) =>
                        cn(
                          'flex items-center justify-between gap-3 px-4 py-3 rounded-lg transition-all duration-200',
                          isActive
                            ? 'bg-primary text-primary-foreground shadow-lg glow'
                            : 'hover:bg-accent hover:text-accent-foreground'
                        )
                      }
                    >
                      <div className="flex items-center gap-3">
                        <item.icon size={20} />
                        <span className="font-medium">{item.label}</span>
                      </div>
                      {item.badge !== undefined && item.badge > 0 && (
                        <Badge variant="warning">
                          {item.badge}
                        </Badge>
                      )}
                    </NavLink>
                  </motion.div>
                ))}
              </nav>
            </motion.aside>
          </>
        )}
      </AnimatePresence>

      {/* Main Content */}
      <main
        className={cn(
          'pt-16 md:pt-20 transition-all duration-300 min-h-screen',
          sidebarOpen ? 'md:pl-64' : 'md:pl-0'
        )}
      >
        <div className="p-4 md:p-6 max-w-[1920px] mx-auto">
          <Outlet />
        </div>
      </main>
    </div>
  )
}
