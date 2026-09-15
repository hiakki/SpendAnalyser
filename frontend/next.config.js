/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Keep isolated verification builds separate from a running local server.
  distDir: process.env.SPENDA_NEXT_DIST_DIR || '.next',
  turbopack: {
    root: __dirname,
  },
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: `${process.env.NEXT_PUBLIC_BACKEND_URL || 'http://127.0.0.1:8000'}/:path*`,
      },
    ]
  },
}
module.exports = nextConfig
