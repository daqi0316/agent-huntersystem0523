module.exports = {
  apps: [
    {
      name: 'ai-recruitment-api',
      script: '.venv/bin/python',
      args: '-m uvicorn app.main:app --host 0.0.0.0 --port 8000 --limit-as=256 --limit-fp-rlimit=1024',
      cwd: '/Users/qixia/agent-huntersystem0523/apps/api',
      env_file: '.env',
      instance_var: 'INSTANCE_ID',

      // ── Auto-restart policy ──────────────────────────────────────────────
      autorestart: true,
      max_restarts: 10,
      max_memory_restart: '750M',         // OOM 时自动重启，避免拖垮系统
      exit_codes: [0, 1, 2],            // 这些退出码才重启，timeout/SIGTERM 等不算
      wait_timeout: 8000,                // 进程启动超时 8s
      kill_timeout: 5000,                // SIGTERM 5s 后 SIGKILL
      shutdown_with_message: true,

      // ── Monitoring ────────────────────────────────────────────────────────
      pmx: true,
      monitor: true,

      // ── Logs ────────────────────────────────────────────────────────────
      out_file: '/tmp/ai-recruitment-api-out.log',
      error_file: '/tmp/ai-recruitment-api-error.log',
      log_date_format: 'YYYY-MM-DD HH:mm:ss',
      merge_logs: true,
    },
  ],
};