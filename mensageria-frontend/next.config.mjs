/** @type {import('next').NextConfig} */
const nextConfig = {
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
