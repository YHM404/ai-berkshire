import fs from 'node:fs';

const app = fs.readFileSync(new URL('../src/App.tsx', import.meta.url), 'utf8');

if (!app.includes('react-markdown')) {
  throw new Error('App.tsx must import react-markdown for detail markdown rendering');
}

if (!app.includes('remark-gfm') || !app.includes('remarkGfm')) {
  throw new Error('App.tsx must enable remark-gfm so tables render in research details');
}

if (/detail\?\.report_md\s*&&\s*<Paragraph>\{detail\.report_md\}<\/Paragraph>/.test(app)) {
  throw new Error('detail.report_md is still rendered as plain Paragraph text');
}

console.log('markdown detail rendering check passed');
