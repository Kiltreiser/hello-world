// Converts numbered pinyin syllables (e.g. "zhen1", "nv3", "de5") into
// Zhuyin (bopomofo) and tone-marked pinyin. All app content is written in
// numbered pinyin and converted here, so Zhuyin is never typed by hand.
(function (global) {
  'use strict';

  const INITIALS = [
    ['zh', 'ㄓ'], ['ch', 'ㄔ'], ['sh', 'ㄕ'],
    ['b', 'ㄅ'], ['p', 'ㄆ'], ['m', 'ㄇ'], ['f', 'ㄈ'],
    ['d', 'ㄉ'], ['t', 'ㄊ'], ['n', 'ㄋ'], ['l', 'ㄌ'],
    ['g', 'ㄍ'], ['k', 'ㄎ'], ['h', 'ㄏ'],
    ['j', 'ㄐ'], ['q', 'ㄑ'], ['x', 'ㄒ'],
    ['r', 'ㄖ'], ['z', 'ㄗ'], ['c', 'ㄘ'], ['s', 'ㄙ'],
  ];

  const FINALS = {
    a: 'ㄚ', o: 'ㄛ', e: 'ㄜ', ai: 'ㄞ', ei: 'ㄟ', ao: 'ㄠ', ou: 'ㄡ',
    an: 'ㄢ', en: 'ㄣ', ang: 'ㄤ', eng: 'ㄥ', er: 'ㄦ', ong: 'ㄨㄥ',
    i: 'ㄧ', ia: 'ㄧㄚ', io: 'ㄧㄛ', ie: 'ㄧㄝ', iao: 'ㄧㄠ', iu: 'ㄧㄡ', iou: 'ㄧㄡ',
    ian: 'ㄧㄢ', in: 'ㄧㄣ', iang: 'ㄧㄤ', ing: 'ㄧㄥ', iong: 'ㄩㄥ',
    u: 'ㄨ', ua: 'ㄨㄚ', uo: 'ㄨㄛ', uai: 'ㄨㄞ', ui: 'ㄨㄟ', uei: 'ㄨㄟ',
    uan: 'ㄨㄢ', un: 'ㄨㄣ', uen: 'ㄨㄣ', uang: 'ㄨㄤ', ueng: 'ㄨㄥ',
    v: 'ㄩ', ve: 'ㄩㄝ', van: 'ㄩㄢ', vn: 'ㄩㄣ',
  };

  const TONE_MARKS = ['', '', 'ˊ', 'ˇ', 'ˋ', '˙'];
  const BUZZ = ['zh', 'ch', 'sh', 'r', 'z', 'c', 's'];

  function parse(syl) {
    const m = /^([a-zü]+)([1-5])$/.exec(syl.toLowerCase().replace(/u:/g, 'v'));
    if (!m) throw new Error('Bad pinyin syllable: ' + syl);
    return { body: m[1].replace(/ü/g, 'v'), tone: Number(m[2]) };
  }

  function toZhuyin(syl) {
    const { body, tone } = parse(syl);
    let initial = '';
    let rest = body;

    if (rest[0] === 'y') {
      if (rest.startsWith('yu')) rest = 'v' + rest.slice(2);
      else if (rest === 'yi' || rest === 'yin' || rest === 'ying') rest = rest.slice(1);
      else rest = 'i' + rest.slice(1);
    } else if (rest[0] === 'w') {
      rest = rest === 'wu' ? 'u' : 'u' + rest.slice(1);
    } else {
      for (const [lat] of INITIALS) {
        if (rest.startsWith(lat)) { initial = lat; rest = rest.slice(lat.length); break; }
      }
    }

    let zhuyin;
    if (BUZZ.includes(initial) && rest === 'i') {
      zhuyin = INITIALS.find(([l]) => l === initial)[1];
    } else {
      if ('jqx'.includes(initial) && initial && rest[0] === 'u') rest = 'v' + rest.slice(1);
      const fin = FINALS[rest];
      if (fin === undefined) throw new Error('Unknown pinyin final in: ' + syl);
      const ini = initial ? INITIALS.find(([l]) => l === initial)[1] : '';
      zhuyin = ini + fin;
    }
    return tone === 5 ? '˙' + zhuyin : zhuyin + TONE_MARKS[tone];
  }

  const ACCENTS = {
    a: 'āáǎà', e: 'ēéěè', i: 'īíǐì', o: 'ōóǒò', u: 'ūúǔù', v: 'ǖǘǚǜ',
  };

  function toPinyin(syl) {
    const { body, tone } = parse(syl);
    let idx;
    if (body.includes('a')) idx = body.indexOf('a');
    else if (body.includes('e')) idx = body.indexOf('e');
    else if (body.includes('ou')) idx = body.indexOf('o');
    else {
      for (let i = body.length - 1; i >= 0; i--) {
        if ('aeiouv'.includes(body[i])) { idx = i; break; }
      }
    }
    let out = body;
    if (tone >= 1 && tone <= 4 && idx !== undefined) {
      out = body.slice(0, idx) + ACCENTS[body[idx]][tone - 1] + body.slice(idx + 1);
    }
    return out.replace(/v/g, 'ü');
  }

  function toneOf(syl) {
    return parse(syl).tone;
  }

  const HAN = /\p{Script=Han}/u;

  // Pairs each Han character with its syllable. Punctuation gets syl: null.
  function annotate(hz, py) {
    const syls = py.trim().split(/\s+/);
    const out = [];
    let i = 0;
    for (const ch of hz) {
      if (HAN.test(ch)) {
        if (i >= syls.length) throw new Error('Not enough pinyin for: ' + hz);
        out.push({ ch, syl: syls[i++] });
      } else {
        out.push({ ch, syl: null });
      }
    }
    if (i !== syls.length) throw new Error('Too much pinyin for: ' + hz);
    return out;
  }

  const api = { toZhuyin, toPinyin, toneOf, annotate, HAN };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else global.Zhuyin = api;
})(this);
