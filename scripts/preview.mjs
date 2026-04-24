import http from 'node:http';
import { readFile } from 'node:fs/promises';
import { resolve, extname } from 'node:path';

const PORT = Number(process.env.PORT ?? 4173);
const root = resolve('./reports');

const contentType = (path) => {
  if (extname(path) === '.md') return 'text/markdown; charset=utf-8';
  if (extname(path) === '.json') return 'application/json; charset=utf-8';
  return 'text/plain; charset=utf-8';
};

const server = http.createServer(async (req, res) => {
  const path = req.url === '/' ? '/README.md' : req.url ?? '/README.md';
  try {
    const data = await readFile(resolve(root, `.${path}`), 'utf8');
    res.writeHead(200, { 'content-type': contentType(path) });
    res.end(data);
  } catch {
    res.writeHead(404, { 'content-type': 'text/plain; charset=utf-8' });
    res.end('Not found');
  }
});

server.listen(PORT, () => {
  console.log(`[preview] reports preview available at http://127.0.0.1:${PORT}`);
});
