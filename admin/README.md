# AnyIDE Admin Dashboard

A premium, modern admin dashboard for AnyIDE with beautiful 3D animations and real-time updates.

## 🚀 Quick Start

**Access:** http://localhost:8080/admin/  
**Default Password:** `admin`

### First Time Setup

1. Navigate to http://localhost:8080/admin/
2. Enter password: `admin`
3. Click "Login"
4. You're in! Start with the HITL Queue page

## Features

- **Real-time HITL Queue**: Approve/reject tool execution requests with live WebSocket updates
- **Audit Log**: Complete history of all tool executions with filtering and search
- **System Health**: Monitor system performance and status
- **Premium UI**: Glassmorphism effects, aurora backgrounds, floating particles, and smooth animations
- **Dark Mode**: Beautiful dark theme optimized for long sessions

## Tech Stack

- **React 18** with TypeScript
- **Vite** for blazing fast development
- **Framer Motion** for smooth animations
- **TailwindCSS** for styling
- **TanStack Query** for data fetching
- **Zustand** for state management
- **WebSocket** for real-time updates

## Usage Guide

### HITL Approval Workflow

1. Go to "HITL Queue" (default page after login)
2. See pending requests appear in real-time
3. Review request details in the right panel
4. Click "Approve" to allow execution or "Reject" to deny
5. Request executes immediately upon approval

### View Audit Log

1. Click "Audit Log" in sidebar
2. Use search box to filter by tool name or parameters
3. Use status dropdown to filter by execution status
4. Click on any row to view full execution details

### Check System Health

1. Click "System Health" in sidebar
2. View key metrics:
   - **Uptime**: How long the container has been running
   - **Pending HITL**: Number of requests waiting for approval
   - **Tools Executed**: Total tool calls since startup
   - **Error Rate**: Percentage of failed tool executions

## Testing the Dashboard

### Trigger a Single HITL Request

```bash
curl -X POST http://localhost:8080/api/tools/fs/write \
  -H "Content-Type: application/json" \
  -d '{"path": "test.conf", "content": "test=value"}'
```

This will:
1. Create a HITL request (because .conf files require approval)
2. Show in the dashboard immediately
3. Play a notification sound
4. Wait for your approval (5-minute timeout)

### Trigger Multiple Requests

```bash
for i in {1..3}; do
  curl -X POST http://localhost:8080/api/tools/fs/write \
    -H "Content-Type: application/json" \
    -d "{\"path\": \"test_$i.conf\", \"content\": \"test=$i\"}" &
done
```

## Visual Features

### Effects
- **Aurora Background**: Animated gradient that moves slowly across the screen
- **Floating Particles**: 20 particles floating up and down with random motion
- **Glassmorphism**: Transparent cards with backdrop blur and subtle borders
- **3D Hover**: Cards lift and tilt on hover with smooth transitions
- **Glow Effects**: Active navigation items glow with primary color
- **Smooth Animations**: All transitions use Framer Motion for fluid motion

### Interactive Elements
- **Countdown Timers**: Show time remaining for HITL requests
- **Progress Bars**: Animate based on time remaining (green → yellow → red)
- **Sound Notifications**: Beep when new HITL request arrives
- **Real-time Updates**: WebSocket pushes updates instantly without polling
- **Search & Filter**: Find specific audit entries quickly with live filtering

## Development

```bash
# Install dependencies
npm install

# Start development server (with hot reload)
npm run dev

# Build for production
npm run build

# Preview production build
npm run preview
```

The development server will proxy API requests to `http://localhost:8080`.

## Production Build

The production build is served as static files from the FastAPI backend at `/admin/`.

```bash
# Build the admin dashboard
cd admin
npm install
npm run build

# The dist/ folder will be copied to static/admin/ in Docker
```

## Configuration

### Change Admin Password

Edit `docker-compose.yaml`:
```yaml
environment:
  - ADMIN_PASSWORD=your-secure-password
```

Then restart:
```bash
docker compose restart anyide
```

### Change Port

Edit `docker-compose.yaml`:
```yaml
ports:
  - "9000:8080"  # Change 9000 to your desired port
```

Access at: http://localhost:9000/admin/

### Customize Colors

Edit `src/index.css` to customize the color scheme:

```css
:root {
  --primary: 221.2 83.2% 53.3%;
  --background: 222.2 84% 4.9%;
  --foreground: 210 40% 98%;
  /* ... */
}
```

### Customize Animations

Adjust animation durations in `tailwind.config.js`:

```javascript
animation: {
  'fade-in': 'fade-in 0.5s ease-out',
  'glow': 'glow 2s ease-in-out infinite',
  'float': 'float 6s ease-in-out infinite',
}
```

## Architecture

### Key Components

#### Effects
- **AuroraBackground**: Animated gradient background with moving colors
- **FloatingParticles**: Subtle particle animations for depth

#### UI Components
- **Card**: Glassmorphic cards with hover effects and shadows
- **Button**: Animated buttons with multiple variants (default, destructive, outline)
- **Badge**: Status badges with semantic colors (success, error, warning)
- **Input**: Styled form inputs with focus states

#### Pages
- **LoginPage**: Secure admin authentication with animated background
- **HITLQueuePage**: Real-time approval queue with WebSocket updates
- **AuditLogPage**: Execution history with search and filtering
- **SystemHealthPage**: System metrics and status monitoring

### WebSocket Protocol

The dashboard connects to `/ws/hitl` for real-time updates:

```typescript
// Incoming messages
{ type: 'hitl_request', data: HITLRequest }      // New request created
{ type: 'hitl_update', data: HITLRequest }       // Request status changed
{ type: 'pending_requests', data: HITLRequest[] } // Initial state on connect

// Outgoing messages
{ type: 'hitl_decision', data: { id, decision, note } } // Approve/reject
```

### Authentication

Session-based authentication with httponly cookies:

1. POST `/admin/api/login` with password
2. Receive session cookie (httponly, secure, SameSite=Lax)
3. All subsequent requests include the cookie automatically
4. Session expires after 24 hours

## Understanding Metrics

### Audit Log Status Codes

- **success**: Tool executed successfully
- **error**: Tool execution failed (check error message)
- **blocked**: Tool was blocked by policy rules
- **hitl_approved**: Tool was approved by admin and executed
- **hitl_rejected**: Tool was rejected by admin
- **hitl_expired**: HITL request timed out (no decision within TTL)

### System Health Indicators

- **Uptime**: Container uptime in seconds (formatted as human-readable)
- **Pending HITL**: Current number of requests awaiting approval
- **Tools Executed**: Total tool calls since container start
- **Error Rate**: Percentage of failed executions (0.0 - 1.0)

## Troubleshooting

### Blank Page

1. Check browser console (F12) for JavaScript errors
2. Verify assets are loading (Network tab)
3. Check container logs: `docker compose logs anyide`
4. Try hard refresh: Ctrl+Shift+R (or Cmd+Shift+R on Mac)

### Login Fails

1. Verify password in `docker-compose.yaml`
2. Test API directly:
   ```bash
   curl -X POST http://localhost:8080/admin/api/login \
     -H "Content-Type: application/json" \
     -d '{"password": "admin"}'
   ```
3. Check container logs for authentication errors

### WebSocket Not Connecting

1. Check browser console for WebSocket errors
2. Verify endpoint is accessible:
   ```bash
   curl -I http://localhost:8080/ws/hitl
   ```
3. Check firewall settings (WebSocket uses same port as HTTP)
4. Verify container is running: `docker compose ps`

### No HITL Requests Appearing

1. Verify WebSocket is connected (check browser console)
2. Trigger a test request (see Testing section above)
3. Check container logs for HITL creation:
   ```bash
   docker compose logs anyide | grep hitl
   ```

### Page Refresh Shows 404

This was fixed in the latest version. If you still see this:
1. Rebuild the container: `docker compose build`
2. Restart: `docker compose up -d`
3. Clear browser cache

## Best Practices

### For Admins

1. Keep the dashboard open in a dedicated browser tab
2. Enable sound notifications for new requests
3. Review HITL requests promptly (5-minute timeout)
4. Check audit log regularly for unusual activity
5. Monitor system health for error rate spikes

### For Developers

1. Use the audit log to debug tool executions
2. Check system health for error rates and patterns
3. Monitor pending HITL count during testing
4. Review rejected requests to understand policy violations
5. Use search/filter in audit log to find specific executions

## Mobile Access

The dashboard is fully responsive and works on:
- iOS Safari
- Chrome Mobile
- Firefox Mobile

Access the same URL from your mobile device on the same network.

## Keyboard Shortcuts

- **Tab**: Navigate between elements
- **Enter**: Submit forms / Click buttons
- **Escape**: Close modals (future feature)
- **Arrow Keys**: Navigate lists (future feature)

## Security Notes

- Sessions expire after 24 hours
- Cookies are httponly (not accessible via JavaScript)
- All API calls require authentication
- WebSocket connections are authenticated via session cookie
- Secrets are never sent to the frontend
- CSRF protection via SameSite cookie attribute

## Design Inspiration

This dashboard takes inspiration from premium design systems:

- **Magic UI** (magicui.design): Animated components and effects
- **Aceternity UI** (ui.aceternity.com): 3D card effects and glassmorphism
- **21st.dev**: Component patterns and layouts
- **TypeGPU** (docs.swmansion.com/TypeGPU): Performance-focused animations

## Browser Support

- Chrome/Edge 90+
- Firefox 88+
- Safari 14+
- Mobile browsers (iOS Safari, Chrome Mobile)

## Additional Resources

- **Validation Report**: See `development/SLICE3_VALIDATION_REPORT.md`
- **Test Script**: Run `bash development/test_slice3.sh`
- **Bug Fixes**: See `development/BUG_FIXES_COMPLETE.md`
- **Troubleshooting Guide**: See `development/ADMIN_DASHBOARD_GUIDE.md`

## Need Help?

1. Check browser console (F12) for errors
2. Check container logs: `docker compose logs anyide -f`
3. Verify health endpoint: `curl http://localhost:8080/health`
4. Review documentation in `development/` folder
5. Check WebSocket connection in Network tab (filter by WS)

---

**Version:** 0.1.0  
**Last Updated:** February 28, 2026  
**Status:** Production Ready ✅

## License

Part of the AnyIDE project.
