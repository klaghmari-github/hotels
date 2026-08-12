/**
 * PM2 — release_1_0_0 sur Adixon
 *
 * Apache (existant, non modifié ici) :
 *   /studio → http://127.0.0.1:8001/studio  (compat legacy → redirect /admin)
 *   /       → http://127.0.0.1:8000/        (app unique user + admin + API)
 *
 * App unique Flask (run.py serve) :
 *   /user   — interface directeur
 *   /admin  — studio admin (auth)
 *   /api/*  — API
 */
module.exports = {
  apps: [
    {
      name: "rod-ia-user",
      cwd: "/var/www/rod-ia",
      script: "run.py",
      interpreter: "/var/www/rod-ia/.venv/bin/python",
      args: "serve --host 127.0.0.1 --port 8000",
      instances: 1,
      exec_mode: "fork",
      autorestart: true,
      max_restarts: 40,
      min_uptime: "8s",
      max_memory_restart: "1200M",
      watch: false,
      env: {
        PYTHONUNBUFFERED: "1",
        ROD_HOST: "127.0.0.1",
        ROD_PORT: "8000",
      },
      out_file: "/var/log/rod-ia/user.out.log",
      error_file: "/var/log/rod-ia/user.error.log",
      merge_logs: true,
      time: true,
    },
    {
      // Compat Apache ProxyPass /studio → :8001/studio
      // Redirige vers /admin sur le vhost principal (même app, port 8000).
      name: "rod-ia-admin",
      cwd: "/var/www/rod-ia",
      script: "scripts/studio_redirect.py",
      interpreter: "/var/www/rod-ia/.venv/bin/python",
      args: "--host 127.0.0.1 --port 8001",
      instances: 1,
      exec_mode: "fork",
      autorestart: true,
      max_restarts: 20,
      min_uptime: "3s",
      max_memory_restart: "80M",
      watch: false,
      env: {
        PYTHONUNBUFFERED: "1",
        ROD_PUBLIC_BASE: "https://rod-ia.adixon-dev.fr",
      },
      out_file: "/var/log/rod-ia/admin.out.log",
      error_file: "/var/log/rod-ia/admin.error.log",
      merge_logs: true,
      time: true,
    },
  ],
};
