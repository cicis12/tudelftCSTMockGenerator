import { cpSync, mkdirSync } from 'node:fs';
mkdirSync('app/static/vendor', { recursive: true });
for (const name of ['katex.min.css', 'katex.min.js', 'fonts']) cpSync(`node_modules/katex/dist/${name}`, `app/static/vendor/${name}`, { recursive: true });
cpSync('node_modules/katex/dist/contrib/auto-render.min.js', 'app/static/vendor/auto-render.min.js');
cpSync('node_modules/katex/LICENSE', 'app/static/vendor/KATEX-LICENSE');
