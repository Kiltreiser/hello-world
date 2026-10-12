// Checks that every piece of content has one valid pinyin syllable per
// character and converts cleanly to Zhuyin. Run: node manman/tools/validate.js
'use strict';
const path = require('path');
const Z = require(path.join(__dirname, '../js/zhuyin.js'));
const { DECKS, ITEMS, SCENES } = require(path.join(__dirname, '../js/data.js'));

let errors = 0;
const seen = new Set();
function check(label, hz, py) {
  try {
    for (const { syl } of Z.annotate(hz, py)) if (syl) Z.toZhuyin(syl);
  } catch (e) {
    errors++;
    console.error(`${label}: ${e.message}`);
  }
}

for (const deck of DECKS) {
  const items = ITEMS[deck.id];
  if (!items) { errors++; console.error('Missing deck items: ' + deck.id); continue; }
  for (const [hz, py, en] of items) {
    if (seen.has(hz)) { errors++; console.error('Duplicate item: ' + hz); }
    seen.add(hz);
    if (!en) { errors++; console.error('Missing English: ' + hz); }
    check(deck.id, hz, py);
  }
}
for (const scene of SCENES) {
  for (const [who, hz, py] of scene.lines) {
    if (who !== 'npc' && who !== 'you') { errors++; console.error('Bad speaker in ' + scene.id); }
    check(scene.id, hz, py);
  }
}

// Spot checks for the converter itself.
const cases = {
  zhen1: 'ㄓㄣ', zhu1: 'ㄓㄨ', nai3: 'ㄋㄞˇ', cha2: 'ㄔㄚˊ', shi4: 'ㄕˋ', zi5: '˙ㄗ',
  nv3: 'ㄋㄩˇ', qu4: 'ㄑㄩˋ', yue4: 'ㄩㄝˋ', you3: 'ㄧㄡˇ', wei2: 'ㄨㄟˊ', wen2: 'ㄨㄣˊ',
  yi2: 'ㄧˊ', ying1: 'ㄧㄥ', yong4: 'ㄩㄥˋ', wu2: 'ㄨˊ', er4: 'ㄦˋ', jiu3: 'ㄐㄧㄡˇ',
  gui3: 'ㄍㄨㄟˇ', lun2: 'ㄌㄨㄣˊ', xiong1: 'ㄒㄩㄥ', xue2: 'ㄒㄩㄝˊ', ri4: 'ㄖˋ',
  o5: '˙ㄛ', jue2: 'ㄐㄩㄝˊ', yuan2: 'ㄩㄢˊ', mo2: 'ㄇㄛˊ', weng1: 'ㄨㄥ',
};
for (const [py, want] of Object.entries(cases)) {
  const got = Z.toZhuyin(py);
  if (got !== want) { errors++; console.error(`toZhuyin(${py}) = ${got}, want ${want}`); }
}
const pyCases = { hao3: 'hǎo', xie4: 'xiè', nv3: 'nǚ', gui3: 'guǐ', jiu3: 'jiǔ', zi5: 'zi', dou4: 'dòu' };
for (const [py, want] of Object.entries(pyCases)) {
  const got = Z.toPinyin(py);
  if (got !== want) { errors++; console.error(`toPinyin(${py}) = ${got}, want ${want}`); }
}

const total = Object.values(ITEMS).reduce((n, a) => n + a.length, 0);
if (errors) { console.error(`\n${errors} problem(s) found.`); process.exit(1); }
console.log(`OK: ${total} items in ${DECKS.length} decks, ${SCENES.length} scenes.`);
