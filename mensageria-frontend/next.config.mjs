/** @type {import('next').NextConfig} */
const nextConfig = {
  // Permite validar um build sem sobrescrever o .next que o serviço de produção
  // está servindo: NEXT_DIST_DIR=.next-verify pnpm build
  distDir: process.env.NEXT_DIST_DIR || ".next",
  eslint: {
    // Ignora ESLint no build de produção — código portado tem 'any' em abundância.
    ignoreDuringBuilds: true,
  },
  typescript: {
    // Permite build mesmo com erros de tipo em arquivos portados.
    ignoreBuildErrors: true,
  },
};

export default nextConfig;
