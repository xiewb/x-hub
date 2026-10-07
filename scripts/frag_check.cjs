// 片段编译定位：找出 v-else 区域内导致 "missing end tag" 的最小片段
const { parse, compileTemplate } = require('@vue/compiler-sfc');
const fs = require('fs');

const src = fs.readFileSync('src/components/NoteEditor.vue', 'utf-8');
const { descriptor } = parse(src, { filename: 'm.vue' });
const lines = descriptor.template.content.split('\n');

// 找 v-else 行（16, 0-based 15）与其配对 </template>
let depth = 0, closeLine = -1;
for (let i = 15; i < lines.length; i++) {
  const opens = (lines[i].match(/<template[\s>]/g) || []).length;
  const closes = (lines[i].match(/<\/template\s*>/g) || []).length;
  depth += opens - closes;
  if (depth === 0) { closeLine = i; break; }
}
console.log('v-else: 16 ..', closeLine + 1, '(1-based)');

const frag = lines.slice(15, closeLine + 1).join('\n');
function fragErr(n) {
  // 取片段前 n 行，闭合片段内打开的 div/header 等后再包一层
  const seg = lines.slice(15, 15 + n).join('\n');
  const t = '<div>\n' + seg + '\n</div>\n</template>\n</div>';
  const r = compileTemplate({ source: t, filename: 'f.vue', id: 'f' });
  return r.errors.filter(e => e.message === 'Element is missing end tag.');
}
console.log('整片段 missing-end-tag 错误数:', fragErr(closeLine - 14).length);

// 二分：最小前缀 n 使 missing-end-tag 出现
let lo = 1, hi = closeLine - 14;
while (lo < hi) {
  const mid = (lo + hi) >> 1;
  if (fragErr(mid).length) hi = mid; else lo = mid + 1;
}
console.log('片段内首个出错前缀行数:', lo);
console.log(lines.slice(15 + lo - 3, 15 + lo + 1).map((l, i) => (lo - 2 + i) + ': ' + l).join('\n'));
