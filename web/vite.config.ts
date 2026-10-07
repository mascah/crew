import { defineConfig, loadEnv } from 'vite'

// The service answers reads only for the configured Tailscale login, a header
// Tailscale Serve adds in production. For local dev, run the service
// (`uv run python -m crew service`) and start Vite with CREW_DEV_LOGIN set to a
// login from its `viewer_logins`; this proxy adds the header. Without it the
// page shows its 403 message. CREW_DEV_API points at a service on another port.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '.', 'CREW_')
  return {
    base: './', // the service serves dist at whatever path Serve mounts
    server: {
      proxy: {
        '/api': {
          target: env.CREW_DEV_API ?? 'http://127.0.0.1:8787',
          headers: { 'Tailscale-User-Login': env.CREW_DEV_LOGIN ?? '' },
        },
      },
    },
  }
})
