// AST 分析：定位 v-else 模板为何缺 end tag
const { parse, compileTemplate } = require('@vue/compiler-sfc');
const { baseParse } = require('@vue/compiler-core');
const fs = require('fs');

const src = fs.readFileSync('src/components/NoteEditor.vue', 'utf-8');
const { descriptor } = parse(src, { filename: 'm.vue' });
const content = descriptor.template.content;
const r = compileTemplate({ source: content, filename: 'm.vue', id: 't' });
console.log('errors:', r.errors.map(e => e.message + (e.loc ? ' @line' + e.loc.start.line : '')));

const ast = baseParse(content);
const tree = [];
function walk(n, d) {
  if (n.type !== 1) return;
  const ln = n.loc && n.loc.start ? n.loc.start.line : '?';
  tree.push('  '.repeat(d) + n.tag + ' L' + ln);
  for (const c of n.children || []) walk(c, d + 1);
}
walk(ast, 0);
// 打印深度 <= 4 的骨架
console.log(tree.filter(l => (l.match(/  /g) || []).length <= 4).join('\n'));
