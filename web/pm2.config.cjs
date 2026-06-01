// PM2 配置文件
// 使用: pm2 start pm2.config.cjs
// 停止: pm2 stop pm2.config.cjs
// 重启: pm2 restart pm2.config.cjs
// 生产模式: pm2 start pm2.config.cjs --env production

module.exports = {
  apps: [
    {
      name: 'zensers-web',
      script: 'node_modules/next/dist/bin/next',
      args: 'dev',
      cwd: __dirname,
      env: {
        NODE_ENV: 'development',
        PORT: '3000',
      },
      env_production: {
        args: 'start',
        NODE_ENV: 'production',
      },
      // 日志
      log_date_format: 'YYYY-MM-DD HH:mm:ss',
      error_file: '../logs/web-error.log',
      out_file: '../logs/web-out.log',
      merge_logs: true,
      // 进程管理
      max_restarts: 10,
      restart_delay: 3000,
      // 优雅关闭
      kill_timeout: 5000,
      // 监听文件变化自动重启
      watch: false,
    },
  ],
};
