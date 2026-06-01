const fs = require('fs');
const path = require('path');

const versionFile = path.join(__dirname, '..', 'VERSION');
const version = fs.existsSync(versionFile)
  ? fs.readFileSync(versionFile, 'utf-8').trim()
  : '0.0.0';

/** @type {import('next').NextConfig} */
const nextConfig = {
  // 允许从后端加载图片
  images: {
    remotePatterns: [
      {
        protocol: 'http',
        hostname: 'localhost',
        port: '8000',
      },
    ],
  },
  // 严格模式
  reactStrictMode: true,

  env: {
    NEXT_PUBLIC_APP_VERSION: version,
    NEXT_PUBLIC_BUILD_DATE: new Date().toISOString().split('T')[0],
  },

  // API 代理 - 仅在未配置 NEXT_PUBLIC_API_URL 时启用
  // 本地开发 / 桌面模式：前端相对路径 → rewrites → 后端
  // 远程部署：NEXT_PUBLIC_API_URL 配置时直连后端，无需 rewrites
  async rewrites() {
    if (!process.env.NEXT_PUBLIC_API_URL) {
      return [
        {
          source: '/api/:path*',
          destination: 'http://localhost:8000/api/:path*',
        },
      ];
    }
    return [];
  },
};

module.exports = nextConfig;