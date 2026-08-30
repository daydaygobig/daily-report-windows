import fs from "node:fs/promises";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath, pathToFileURL } from "node:url";
import { execFile } from "node:child_process";
import { promisify } from "node:util";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(__dirname, "../..");
const execFileAsync = promisify(execFile);

function loadResvg() {
  try {
    const localRequire = createRequire(path.join(__dirname, "package.json"));
    return localRequire("@resvg/resvg-js").Resvg;
  } catch {
    const labRequire = createRequire(path.join(repoRoot, "artifacts/workplace-card-render-lab/package.json"));
    return labRequire("@resvg/resvg-js").Resvg;
  }
}

const Resvg = loadResvg();
const singleRenderScale = 4;
const collectionRenderScale = 2;
const feishuMaxImageBytes = 10 * 1024 * 1024;
const feishuMaxImageDimension = 12000;

function scaleForLayout(layout) {
  return layout === "collection" ? collectionRenderScale : singleRenderScale;
}

function boundedScale(width, height, preferredScale) {
  const maxBaseDimension = Math.max(width, height);
  if (maxBaseDimension > feishuMaxImageDimension) {
    throw new Error(`图片原始尺寸 ${width}x${height} 已超过飞书 ${feishuMaxImageDimension}x${feishuMaxImageDimension} 限制，请减少合集话题数或改为单卡推送`);
  }
  return Math.max(1, Math.min(preferredScale, Math.floor(feishuMaxImageDimension / maxBaseDimension)));
}

function isFeishuImageSizeOk(meta) {
  return meta.width <= feishuMaxImageDimension && meta.height <= feishuMaxImageDimension && meta.size <= feishuMaxImageBytes;
}

async function loadSatori() {
  try {
    const localRequire = createRequire(path.join(__dirname, "package.json"));
    const mod = await import(pathToFileURL(localRequire.resolve("satori")).href);
    return mod.default?.default || mod.default;
  } catch {
    const labRequire = createRequire(path.join(repoRoot, "artifacts/workplace-card-render-lab/package.json"));
    const mod = await import(pathToFileURL(labRequire.resolve("satori")).href);
    return mod.default?.default || mod.default;
  }
}

const cardWidth = 400;
const longPadding = 32;
const longGap = 24;
const palette = {
  page: "#f3f4f6",
  longBg: "#ebeef2",
  ink: "#1f2937",
  body: "#374151",
  muted: "#6b7280",
  tagText: "#374151"
};

const themes = {
  amber: { main: "#f59e0b", light: "#fef3c7", dark: "#b45309", bg: "#fffbeb" },
  blue: { main: "#2563eb", light: "#dbeafe", dark: "#1d4ed8", bg: "#eff6ff" },
  green: { main: "#10b981", light: "#d1fae5", dark: "#047857", bg: "#f0fdf4" },
  neutral: { main: "#6366f1", light: "#e0e7ff", dark: "#4338ca", bg: "#f5f3ff" }
};

const topicTypeStyles = {
  industry_business: { styleKey: "style_a", theme: "amber" },
  work_methods: { styleKey: "style_b", theme: "blue" },
  career_growth: { styleKey: "style_c", theme: "green" },
  mind_wellbeing: { styleKey: "style_d", theme: "neutral" }
};

function arg(name, fallback = null) {
  const index = process.argv.indexOf(`--${name}`);
  if (index < 0) return fallback;
  return process.argv[index + 1] ?? fallback;
}

function esc(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

const emojiAssetCache = new Map();
const emojiPattern = () => /\p{Extended_Pictographic}(?:\uFE0F|\uFE0E)?(?:\u200D\p{Extended_Pictographic}(?:\uFE0F|\uFE0E)?)*/gu;
const emojiCharPattern = /\p{Extended_Pictographic}/u;
const variationSelectorPattern = /[\uFE0E\uFE0F\u200D]/u;

function emojiCodepoints(value) {
  return Array.from(value)
    .map((char) => char.codePointAt(0))
    .filter((code) => code && code !== 0xfe0f && code !== 0xfe0e)
    .map((code) => code.toString(16))
    .join("-");
}

function splitEmojiText(value) {
  const text = String(value ?? "");
  const pattern = emojiPattern();
  const parts = [];
  let cursor = 0;
  for (const match of text.matchAll(pattern)) {
    const index = match.index ?? 0;
    if (index > cursor) parts.push({ type: "text", value: text.slice(cursor, index) });
    parts.push({ type: "emoji", value: match[0] });
    cursor = index + match[0].length;
  }
  if (cursor < text.length) parts.push({ type: "text", value: text.slice(cursor) });
  return parts;
}

function collectEmojis(value, output) {
  for (const match of String(value ?? "").matchAll(emojiPattern())) {
    const codepoints = emojiCodepoints(match[0]);
    if (codepoints) output.add(codepoints);
  }
}

function collectEmojiValues(value, output) {
  for (const match of String(value ?? "").matchAll(emojiPattern())) {
    const codepoints = emojiCodepoints(match[0]);
    if (codepoints) output.set(match[0], codepoints);
  }
}

async function preloadEmojiAssets(cards) {
  const codepoints = new Set();
  for (const card of cards) {
    [
      card.title,
      card.time_range,
      card.trigger_quote,
      card.initiator_label,
      card.initiator,
      card.summary,
      card.background,
      card.relationship,
      card.solution,
      card.highlight_label,
      card.highlight_quote,
      card.highlight_speaker,
      ...(card.tags || []),
      ...(card.points || []),
      ...(card.analysis || []),
      ...(card.participants || [])
    ].forEach((value) => collectEmojis(value, codepoints));
  }
  await Promise.all(
    [...codepoints].map(async (code) => {
      if (emojiAssetCache.has(code)) return;
      try {
        const response = await fetch(`https://cdn.jsdelivr.net/gh/twitter/twemoji@14.0.2/assets/svg/${code}.svg`);
        if (!response.ok) {
          emojiAssetCache.set(code, null);
          return;
        }
        const svg = await response.text();
        emojiAssetCache.set(code, `data:image/svg+xml;base64,${Buffer.from(svg).toString("base64")}`);
      } catch {
        emojiAssetCache.set(code, null);
      }
    })
  );
}

function inlineTextWidth(text, size) {
  return splitEmojiText(text).reduce((sum, part) => {
    if (part.type === "emoji") return sum + emojiInlineWidth(size);
    return sum + textWidth(part.value, size);
  }, 0);
}

function emojiInlineWidth(size) {
  return size * 1.32;
}

function svgInlineText(text, x, y, size, options = {}) {
  const {
    fill = palette.ink,
    weight = 400,
    family = "Microsoft YaHei, SimHei, sans-serif",
    anchor = "start",
  } = options;
  const parts = splitEmojiText(text);
  let cursorX = anchor === "middle" ? x - inlineTextWidth(text, size) / 2 : anchor === "end" ? x - inlineTextWidth(text, size) : x;
  let output = "";
  for (const part of parts) {
    if (part.type === "emoji") {
      const width = emojiInlineWidth(size);
      const imageSize = size * 1.08;
      const imageX = cursorX + (width - imageSize) / 2;
      const href = emojiAssetCache.get(emojiCodepoints(part.value));
      if (href) {
        output += `<image href="${href}" x="${imageX}" y="${y - size * 0.85}" width="${imageSize}" height="${imageSize}" preserveAspectRatio="xMidYMid meet"/>`;
      } else {
        output += `<text x="${imageX}" y="${y}" font-family="Segoe UI Emoji, ${family}" font-size="${size}" font-weight="${weight}" fill="${fill}">${esc(part.value)}</text>`;
      }
      cursorX += width;
    } else if (part.value) {
      output += `<text x="${cursorX}" y="${y}" font-family="${family}" font-size="${size}" font-weight="${weight}" fill="${fill}">${esc(part.value)}</text>`;
      cursorX += textWidth(part.value, size);
    }
  }
  return output;
}

function satoriGraphemeImages(cards) {
  const values = new Map();
  for (const card of cards) {
    [
      card.title,
      card.time_range,
      card.trigger_quote,
      card.initiator_label,
      card.initiator,
      card.summary,
      card.background,
      card.relationship,
      card.solution,
      card.highlight_label,
      card.highlight_quote,
      card.highlight_speaker,
      ...(card.tags || []),
      ...(card.points || []),
      ...(card.analysis || []),
      ...(card.participants || [])
    ].forEach((value) => collectEmojiValues(value, values));
  }
  return Object.fromEntries(
    [...values.entries()]
      .map(([emoji, code]) => [emoji, emojiAssetCache.get(code)])
      .filter((entry) => Boolean(entry[1]))
  );
}

function charWidth(ch, size) {
  if (variationSelectorPattern.test(ch)) return 0;
  if (emojiCharPattern.test(ch)) return emojiInlineWidth(size);
  if (/[A-Za-z0-9]/.test(ch)) return size * 0.56;
  if (/\s/.test(ch)) return size * 0.32;
  if (/[,.;:'"!?()[\]{}<>/\\|`~@#$%^&*_+=-]/.test(ch)) return size * 0.42;
  return size * 0.98;
}

function textWidth(text, size) {
  return [...String(text ?? "")].reduce((sum, ch) => sum + charWidth(ch, size), 0);
}

function wrapText(text, size, maxWidth, maxLines = Infinity) {
  const chars = [...String(text ?? "")];
  const lines = [];
  let current = "";
  let width = 0;
  for (const ch of chars) {
    const w = charWidth(ch, size);
    if (current && width + w > maxWidth) {
      lines.push(current);
      current = ch.trimStart();
      width = textWidth(current, size);
      if (lines.length >= maxLines) break;
    } else {
      current += ch;
      width += w;
    }
  }
  if (current && lines.length < maxLines) lines.push(current);
  if (!lines.length) lines.push("");
  if (lines.length === maxLines && chars.length > [...lines.join("")].length) {
    lines[lines.length - 1] = lines[lines.length - 1].replace(/.{1,2}$/, "…");
  }
  return lines;
}

function layoutTags(tags, size, maxWidth) {
  const rows = [];
  let row = [];
  let hidden = 0;
  const maxRows = 2;
  const rowWidthOf = (items) => items.reduce((sum, item, index) => sum + item.width + (index > 0 ? 6 : 0), 0);
  for (const tag of tags) {
    const w = Math.ceil(inlineTextWidth(tag, size) + 18);
    if (row.length && rowWidthOf(row) + 6 + w > maxWidth) {
      rows.push(row);
      row = [];
    }
    if (rows.length >= maxRows) {
      hidden += 1;
      continue;
    }
    row.push({ text: tag, width: w });
  }
  if (row.length) rows.push(row);
  if (hidden > 0) {
    if (!rows.length) rows.push([]);
    const target = rows[Math.min(rows.length - 1, maxRows - 1)];
    const text = "等";
    const hiddenTag = { text, width: Math.ceil(textWidth(text, size) + 18) };
    while (target.length && rowWidthOf(target) + 6 + hiddenTag.width > maxWidth) {
      target.pop();
      hidden += 1;
      hiddenTag.text = "等";
      hiddenTag.width = Math.ceil(textWidth(hiddenTag.text, size) + 18);
    }
    if (!target.length || rowWidthOf(target) + (target.length ? 6 : 0) + hiddenTag.width <= maxWidth) {
      target.push(hiddenTag);
    }
  }
  return rows.slice(0, maxRows);
}

function visibleParticipantTags(participants, size = 13, maxWidth = 292) {
  return layoutTags(participants || [], size, maxWidth).flat().map((tag) => tag.text);
}

function themeOf(card) {
  const theme = card.theme || topicTypeStyles[card.topic_type]?.theme || "blue";
  return themes[theme] || themes.blue;
}

function cardTags(card) {
  const raw = Array.isArray(card.tags) ? card.tags : [];
  const tags = raw.map((tag) => String(tag ?? "").trim()).filter(Boolean);
  return tags.slice(0, 3);
}

function variantOf(card) {
  const styleKey = card.style_key || topicTypeStyles[card.topic_type]?.styleKey || "style_b";
  if (styleKey === "style_a") return "a";
  if (styleKey === "style_b") return "b";
  if (styleKey === "style_c") return "c";
  if (styleKey === "style_d") return "d";
  return "b";
}

function styleOf(card) {
  const theme = themeOf(card);
  const variant = variantOf(card);
  const base = {
    variant,
    theme,
    cardFill: "#ffffff",
    headerFill: "#ffffff",
    bodyFill: "#fcfcfd",
    textBoxFill: "#ffffff",
    textBoxStroke: "#f3f4f6",
    highlightFill: theme.bg,
    highlightStroke: theme.light,
    participantFill: "#f3f4f6",
    participantStroke: "#e5e7eb",
    topFill: theme.main,
    cardStroke: "rgba(0,0,0,0.06)",
    radius: 12
  };
  if (variant === "a") {
    return {
      ...base,
      topFill: "#111827",
      bodyFill: "#ffffff",
      cardStroke: "#d1d5db",
      radius: 8
    };
  }
  if (variant === "b") {
    return {
      ...base,
      cardFill: theme.bg,
      headerFill: theme.bg,
      bodyFill: "#ffffff",
      cardStroke: theme.light,
      radius: 16,
      participantFill: "#ffffff"
    };
  }
  if (variant === "c") {
    return {
      ...base,
      bodyFill: "#f4f5f7",
      textBoxFill: "#ffffff",
      participantFill: "#ffffff",
      cardStroke: "#d1d5db",
      radius: 8
    };
  }
  return {
    ...base,
    cardFill: theme.bg,
    headerFill: theme.bg,
    bodyFill: theme.bg,
    textBoxFill: "rgba(255,255,255,0.72)",
    textBoxStroke: "rgba(255,255,255,0.92)",
    highlightFill: "rgba(255,255,255,0.72)",
    highlightStroke: "rgba(255,255,255,0.92)",
    participantFill: "rgba(255,255,255,0.72)",
    participantStroke: "rgba(255,255,255,0.92)",
    cardStroke: theme.light,
    radius: 8
  };
}

function measure(card) {
  const variant = variantOf(card);
  const titleLines = wrapText(card.title, 22, 352, 3);
  const searchLines = wrapText(`爬楼关键词：${card.trigger_quote}`, 13, 322, 4);
  const triggerLines = wrapText(`“${card.trigger_quote}”`, 15, 322, 5);
  const summaryLines = wrapText(card.summary, 15, 322, 7);
  const pointMaxWidth = variant === "c" ? 282 : variant === "d" ? 296 : 320;
  const pointLines = card.points.map((point) => wrapText(point, 15, pointMaxWidth, 4));
  const highlightLines = wrapText(card.highlight_quote, 17, 304, 5);
  const participantRows = layoutTags(card.participants, 13, 292);
  const headerHeight = 22 + titleLines.length * 27 + 12 + 22 + 20 + 6;
  const searchHeight = 20 + searchLines.length * 19;
  const sectionHeight = variant === "c" || variant === "d" ? 40 : 35;
  const pointGap = variant === "c" ? 24 : 12;
  const triggerHeight = sectionHeight + 27 + triggerLines.length * 21;
  const pointsInnerPadding = variant === "d" ? 24 : 0;
  const summaryHeight = sectionHeight + summaryLines.length * 21;
  const pointsHeight = sectionHeight + pointLines.reduce((sum, lines) => sum + Math.max(20, lines.length * 21) + pointGap, 0) + pointsInnerPadding;
  const participantsHeight = Math.max(20, participantRows.length * 27);
  const highlightHeight = 22 + 12 + highlightLines.length * 23 + 44;
  const height =
    20 +
    headerHeight +
    searchHeight +
    24 +
    triggerHeight +
    24 +
    summaryHeight +
    24 +
    pointsHeight +
    20 +
    participantsHeight +
    20 +
    highlightHeight +
    20;
  return {
    height: Math.ceil(height),
    titleLines,
    searchLines,
    searchHeight,
    triggerLines,
    summaryLines,
    pointLines,
    highlightLines,
    participantRows
  };
}

function textLines(lines, x, y, size, options = {}) {
  const { lineHeight = size * 1.35 } = options;
  return lines
    .map((line, index) => svgInlineText(line, x, y + index * lineHeight, size, options))
    .join("\n");
}

function pill(x, y, text, fill, color, size = 13, weight = 700, padX = 8, height = 20) {
  const width = Math.max(28, inlineTextWidth(text, size) + padX * 2);
  return {
    width,
    svg: `<rect x="${x}" y="${y}" width="${width}" height="${height}" rx="4" fill="${fill}"/>${svgInlineText(text, x + width / 2, y + height - 5, size, { fill: color, weight, anchor: "middle" })}`
  };
}

function displayTagsSvg(card, style, x, y, maxWidth) {
  let output = "";
  let tagX = x;
  for (const tag of cardTags(card)) {
    const item = pill(tagX, y, tag, style.theme.light, style.theme.dark);
    if (tagX > x && tagX + item.width > x + maxWidth) break;
    output += item.svg;
    tagX += item.width + 6;
  }
  return output;
}

function participantTags(card, style, x, y, rows) {
  let output = `<text x="${x}" y="${y + 15}" font-family="Microsoft YaHei, SimHei, sans-serif" font-size="13" font-weight="700" fill="${palette.muted}">参与者：</text>`;
  let rowY = y;
  for (const row of rows) {
    let tagX = x + 64;
    for (const tag of row) {
      output += `<rect x="${tagX}" y="${rowY}" width="${tag.width}" height="22" rx="4" fill="${style.participantFill}" stroke="${style.participantStroke}"/>`;
      output += svgInlineText(tag.text, tagX + tag.width / 2, rowY + 16, 13, { fill: palette.tagText, weight: 700, anchor: "middle" });
      tagX += tag.width + 6;
    }
    rowY += 27;
  }
  return output;
}

function cardSvg(card, x = 0, y = 0) {
  const style = styleOf(card);
  const m = measure(card);
  let out = `<g transform="translate(${x} ${y})">`;
  out += `<rect x="0" y="0" width="${cardWidth}" height="${m.height}" rx="${style.radius}" fill="${style.cardFill}" stroke="${style.cardStroke}" filter="url(#shadow)"/>`;
  out += `<rect x="0" y="0" width="${cardWidth}" height="6" fill="${style.topFill}"/>`;
  let cy = 6;
  const headerHeight = 22 + m.titleLines.length * 27 + 12 + 22 + 20;
  out += `<rect x="0" y="${cy}" width="${cardWidth}" height="${headerHeight}" fill="${style.headerFill}"/>`;
  out += textLines(m.titleLines, 24, cy + 42, 22, { fill: "#111827", weight: 900, family: "SimSun, SimHei, serif", lineHeight: 27 });
  const tagY = cy + 22 + m.titleLines.length * 27 + 12;
  out += displayTagsSvg(card, style, 24, tagY, 238);
  out += svgInlineText(card.time_range, cardWidth - 24, tagY + 16, 13, { fill: "#9ca3af", weight: 600, anchor: "end" });
  cy += headerHeight;
  out += `<rect x="0" y="${cy}" width="${cardWidth}" height="${m.height - cy}" fill="${style.bodyFill}"/>`;
  cy += 20;
  const searchFill = style.variant === "d" ? "rgba(255,255,255,0.72)" : style.theme.bg;
  const searchStroke = style.variant === "d" ? "rgba(255,255,255,0.92)" : style.theme.light;
  out += `<rect x="24" y="${cy}" width="352" height="${m.searchHeight}" rx="8" fill="${searchFill}" stroke="${searchStroke}"/>`;
  out += textLines(m.searchLines, 38, cy + 22, 13, { fill: palette.muted, weight: 700, lineHeight: 19 });
  cy += m.searchHeight + 24;

  const section = (num, title) => {
    if (style.variant === "c" || style.variant === "d") {
      const label = `${num} ${title}`;
      const width = Math.min(240, Math.max(108, textWidth(label, 16) + 24));
      out += `<rect x="24" y="${cy}" width="${width}" height="28" rx="4" fill="${style.variant === "c" ? "#111827" : style.theme.dark}"/>`;
      out += svgInlineText(label, 38, cy + 20, 16, { fill: "#ffffff", weight: 900, family: "SimSun, SimHei, serif" });
      cy += 40;
      return;
    }
    out += `<text x="24" y="${cy + 16}" font-family="Microsoft YaHei, SimHei, sans-serif" font-size="16" font-weight="900" fill="${style.theme.main}">${num}</text>`;
    out += svgInlineText(title, 49, cy + 16, 16, { fill: palette.ink, weight: 900, family: "SimSun, SimHei, serif" });
    cy += 33;
  };
  section("01", card.section1_title || "抛出探讨");
  const triggerBlockHeight = 27 + m.triggerLines.length * 21;
  if (style.variant === "b" || style.variant === "c") {
    out += `<rect x="24" y="${cy - 4}" width="352" height="${triggerBlockHeight + 12}" rx="8" fill="${style.textBoxFill}" stroke="${style.textBoxStroke}"/>`;
  }
  out += `<line x1="24" y1="${cy}" x2="24" y2="${cy + triggerBlockHeight}" stroke="${style.theme.main}" stroke-width="4"/>`;
  out += svgInlineText(card.initiator_label, 36, cy + 15, 13, { fill: "#6b7280", weight: 700 });
  out += pill(92, cy, card.initiator, palette.ink, "#ffffff", 12, 800, 8, 20).svg;
  out += textLines(m.triggerLines, 36, cy + 45, 15, { fill: "#111827", weight: 600, lineHeight: 21 });
  cy += triggerBlockHeight + 24;
  section("02", "话题总结");
  const summaryHeight = m.summaryLines.length * 21;
  out += textLines(m.summaryLines, 24, cy + 16, 15, { fill: "#374151", lineHeight: 21 });
  cy += summaryHeight + 24;
  section("03", "大家怎么说");
  if (style.variant === "d") {
    const pointsBoxHeight = m.pointLines.reduce((sum, lines) => sum + Math.max(20, lines.length * 21) + 12, 0) + 20;
    out += `<rect x="24" y="${cy - 8}" width="352" height="${pointsBoxHeight}" rx="8" fill="${style.textBoxFill}" stroke="${style.textBoxStroke}"/>`;
  }
  for (let i = 0; i < card.points.length; i += 1) {
    const pointHeight = Math.max(20, m.pointLines[i].length * 21);
    if (style.variant === "c") {
      out += `<rect x="24" y="${cy - 8}" width="352" height="${pointHeight + 20}" rx="8" fill="#ffffff" stroke="#e5e7eb"/>`;
      out += `<circle cx="40" cy="${cy + 7}" r="10" fill="${style.theme.main}"/>`;
      out += `<text x="40" y="${cy + 13}" text-anchor="middle" font-family="Microsoft YaHei, SimHei, sans-serif" font-size="13" font-weight="900" fill="#ffffff">${i + 1}</text>`;
      out += textLines(m.pointLines[i], 64, cy + 13, 15, { fill: "#1f2937", lineHeight: 21 });
      cy += pointHeight + 24;
    } else if (style.variant === "d") {
      out += `<text x="42" y="${cy + 15}" font-family="Microsoft YaHei, SimHei, sans-serif" font-size="15" font-weight="900" fill="${style.theme.main}">${i + 1}</text>`;
      out += textLines(m.pointLines[i], 64, cy + 15, 15, { fill: "#1f2937", lineHeight: 21 });
      cy += pointHeight + 12;
    } else {
      out += `<text x="24" y="${cy + 15}" font-family="Microsoft YaHei, SimHei, sans-serif" font-size="15" font-weight="900" fill="${style.theme.main}">${i + 1}</text>`;
      out += textLines(m.pointLines[i], 44, cy + 15, 15, { fill: "#1f2937", lineHeight: 21 });
      cy += pointHeight + 12;
    }
  }
  cy += style.variant === "d" ? 24 : 8;
  out += participantTags(card, style, 24, cy, m.participantRows);
  cy += Math.max(20, m.participantRows.length * 27) + 20;
  const highlightHeight = 22 + 12 + m.highlightLines.length * 23 + 44;
  out += `<rect x="24" y="${cy}" width="352" height="${highlightHeight}" rx="8" fill="${style.highlightFill}" stroke="${style.highlightStroke}"/>`;
  out += svgInlineText(card.highlight_label || "高光时刻", 44, cy + 26, 13, { fill: style.theme.dark, weight: 900 });
  out += textLines(m.highlightLines, 44, cy + 61, 17, { fill: "#111827", weight: 700, lineHeight: 23 });
  out += svgInlineText(`— ${card.highlight_speaker}`, 356, cy + highlightHeight - 15, 13, { fill: style.theme.dark, weight: 700, anchor: "end" });
  out += `</g>`;
  return { svg: out, height: m.height };
}

function rootSvg(width, height, body, background = "transparent") {
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">
  <defs><filter id="shadow" x="-20%" y="-20%" width="140%" height="140%"><feDropShadow dx="0" dy="10" stdDeviation="10" flood-color="#000000" flood-opacity="0.06"/></filter></defs>
  <rect width="${width}" height="${height}" fill="${background}"/>
  ${body}
</svg>`;
}

async function writePng(svg, file, scale = singleRenderScale) {
  await fs.mkdir(path.dirname(file), { recursive: true });
  const baseWidth = Number(svg.match(/width="(\d+)"/)?.[1] || cardWidth);
  const baseHeight = Number(svg.match(/height="(\d+)"/)?.[1] || cardWidth);
  let nextScale = boundedScale(baseWidth, baseHeight, scale);
  while (nextScale >= 1) {
    const png = new Resvg(svg, { fitTo: { mode: "width", value: baseWidth * nextScale } }).render().asPng();
    const dimensions = pngDimensions(png);
    const meta = { size: png.length, scale: nextScale, ...dimensions };
    if (isFeishuImageSizeOk(meta)) {
      await fs.writeFile(file, png);
      return meta;
    }
    nextScale -= 1;
  }
  throw new Error(`图片超过飞书上传限制：最大 ${feishuMaxImageDimension}x${feishuMaxImageDimension} 且不超过 10MB`);
}

const h = (type, props, ...children) => {
  const nextProps = { ...(props || {}) };
  if (type === "div") {
    nextProps.style = {
      display: nextProps.style?.display || "flex",
      flexDirection: nextProps.style?.flexDirection || "column",
      ...(nextProps.style || {})
    };
  }
  return { type, props: { ...nextProps, children } };
};

function satoriHeight(card) {
  return isCaseCard(card) ? measureCase(card).height : measure(card).height;
}

function isCaseCard(card) {
  return String(card?.card_format || "").toLowerCase() === "case";
}

function cardTreeFor(card) {
  return isCaseCard(card) ? caseCardTree(card) : topicCardTree(card);
}

// === 案例卡片（六槽位：背景概述/人物关系/分析过程/解决方案/金句） ===

function measureCase(card) {
  const titleLines = wrapText(card.title, 22, 352, 3);
  const backgroundLines = wrapText(card.background, 15, 352, 10);
  const relationshipLines = wrapText(card.relationship, 15, 352, 6);
  const analysisLines = (card.analysis || []).map((point) => wrapText(point, 15, 320, 4));
  const solutionLines = wrapText(card.solution, 15, 316, 6);
  const highlightLines = wrapText(card.highlight_quote, 17, 304, 5);
  const sectionHeight = 34; // 章节标题行 22 + marginBottom 12
  const bodyLine = 23; // fontSize 15 * lineHeight 1.5
  const height =
    6 + // 顶部色条
    20 + titleLines.length * 27 + 12 + 22 + 20 + // 头部（标题+标签行，不展示日期）
    20 + // 正文上内边距
    sectionHeight + backgroundLines.length * bodyLine + 24 + // 01 背景概述
    sectionHeight + relationshipLines.length * bodyLine + 24 + // 02 人物关系
    sectionHeight +
    analysisLines.reduce((sum, lines) => sum + Math.max(22, lines.length * 21) + 12, 0) +
    24 + // 03 分析过程
    sectionHeight + solutionLines.length * bodyLine + 24 + // 04 解决方案
    20 + 20 + 12 + highlightLines.length * 25 + 12 + 21 + 20 + // 金句盒（上下内边距+标签+引文+署名）
    20; // 正文下内边距
  return {
    height: Math.ceil(height),
    titleLines,
    backgroundLines,
    relationshipLines,
    analysisLines,
    solutionLines,
    highlightLines
  };
}

function caseCardTree(card) {
  const style = styleOf(card);
  const height = measureCase(card).height;
  const tags = cardTags(card);
  const paragraph = (text) =>
    h("div", { style: { fontSize: 15, color: palette.body, lineHeight: 1.5 } }, text);
  const sectionBlock = (index, title, content) =>
    h("div", { style: { marginBottom: 24 } }, sectionHeaderTree(style, index, title), content);
  return h(
    "div",
    {
      style: {
        width: cardWidth,
        minHeight: height,
        flexShrink: 0,
        background: style.cardFill,
        overflow: "hidden",
        position: "relative",
        borderRadius: style.radius,
        border: `1px solid ${style.cardStroke}`,
        boxShadow: "0 10px 25px rgba(0,0,0,0.05)",
        fontFamily: "SimHei",
        color: palette.ink,
        letterSpacing: 0
      }
    },
    h("div", { style: { height: 6, background: style.topFill, width: "100%", flexShrink: 0 } }),
    h(
      "div",
      { style: { padding: "20px 24px", background: style.headerFill, borderBottom: "1px solid rgba(0,0,0,0.04)" } },
      h("div", { style: { fontSize: 22, fontWeight: 900, lineHeight: 1.22, color: "#111827", marginBottom: 12 } }, card.title),
      h(
        "div",
        { style: { flexDirection: "row", alignItems: "center", gap: 6, flexWrap: "wrap", maxWidth: 352 } },
        ...tags.map((tag) =>
          h(
            "div",
            {
              style: {
                background: style.theme.light,
                color: style.theme.dark,
                padding: "2px 8px",
                borderRadius: 4,
                fontSize: 13,
                fontWeight: 800
              }
            },
            tag
          )
        )
      )
    ),
    h(
      "div",
      { style: { padding: "20px 24px", background: style.bodyFill } },
      sectionBlock("01", "背景概述", paragraph(card.background)),
      sectionBlock("02", "人物关系", paragraph(card.relationship)),
      sectionBlock(
        "03",
        "分析过程",
        h(
          "div",
          { style: { gap: 12 } },
          ...(card.analysis || []).map((point, index) =>
            h(
              "div",
              { style: { flexDirection: "row", alignItems: "flex-start", gap: 8 } },
              h("div", { style: { color: style.theme.main, fontSize: 15, fontWeight: 900, marginTop: 1 } }, String(index + 1)),
              h("div", { style: { color: palette.ink, fontSize: 15, lineHeight: 1.45, flex: 1 } }, point)
            )
          )
        )
      ),
      sectionBlock(
        "04",
        "解决方案",
        h(
          "div",
          {
            style: {
              background: style.textBoxFill,
              border: `1px solid ${style.textBoxStroke}`,
              padding: 14,
              borderRadius: 8,
              fontSize: 15,
              color: palette.ink,
              fontWeight: 600,
              lineHeight: 1.5
            }
          },
          card.solution
        )
      ),
      h(
        "div",
        { style: { background: style.highlightFill, border: `1px solid ${style.highlightStroke}`, padding: 20, borderRadius: 8 } },
        h("div", { style: { fontSize: 13, fontWeight: 900, color: style.theme.dark, marginBottom: 12 } }, card.highlight_label || "金句"),
        h("div", { style: { fontSize: 17, fontWeight: 800, color: "#111827", lineHeight: 1.45, marginBottom: 12 } }, `“${card.highlight_quote}”`),
        h("div", { style: { fontSize: 13, fontWeight: 800, color: style.theme.dark, textAlign: "right" } }, `— ${card.highlight_speaker}`)
      )
    )
  );
}

function sectionHeaderTree(style, index, title) {
  if (style.variant === "c" || style.variant === "d") {
    return h(
      "div",
      {
        style: {
          alignSelf: "flex-start",
          background: style.variant === "c" ? "#111827" : style.theme.dark,
          color: "#ffffff",
          padding: "4px 14px",
          borderRadius: 4,
          marginBottom: 12,
          fontFamily: "SimHei",
          fontSize: 16,
          fontWeight: 900
        }
      },
      `${index} ${title}`
    );
  }
  return h(
    "div",
    {
      style: {
        flexDirection: "row",
        alignItems: "center",
        marginBottom: 12,
        fontFamily: "SimHei",
        fontSize: 16,
        fontWeight: 900,
        color: palette.ink
      }
    },
    h("span", { style: { color: style.theme.main, fontSize: 16, fontWeight: 900, marginRight: 6 } }, index),
    title
  );
}

function topicCardTree(card) {
  const style = styleOf(card);
  const height = satoriHeight(card);
  const tags = cardTags(card);
  const participants = visibleParticipantTags(card.participants);
  return h(
    "div",
    {
      style: {
        width: cardWidth,
        minHeight: height,
        flexShrink: 0,
        background: style.cardFill,
        overflow: "hidden",
        position: "relative",
        borderRadius: style.radius,
        border: `1px solid ${style.cardStroke}`,
        boxShadow: "0 10px 25px rgba(0,0,0,0.05)",
        fontFamily: "SimHei",
        color: palette.ink,
        letterSpacing: 0
      }
    },
    h("div", { style: { height: 6, background: style.topFill, width: "100%", flexShrink: 0 } }),
    h(
      "div",
      { style: { padding: "20px 24px", background: style.headerFill, borderBottom: "1px solid rgba(0,0,0,0.04)" } },
      h("div", { style: { fontSize: 22, fontWeight: 900, lineHeight: 1.22, color: "#111827", marginBottom: 12 } }, card.title),
      h(
        "div",
        { style: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" } },
        h(
          "div",
          { style: { flexDirection: "row", alignItems: "center", gap: 6, flexWrap: "wrap", maxWidth: 238 } },
          ...tags.map((tag) =>
            h(
              "div",
              {
                style: {
                  background: style.theme.light,
                  color: style.theme.dark,
                  padding: "2px 8px",
                  borderRadius: 4,
                  fontSize: 13,
                  fontWeight: 800
                }
              },
              tag
            )
          )
        ),
        h("div", { style: { color: "#6b7280", fontSize: 13, fontWeight: 600 } }, card.time_range)
      )
    ),
    h(
      "div",
      { style: { padding: "20px 24px", background: style.bodyFill } },
      h(
        "div",
        {
          style: {
            background: style.variant === "d" ? "rgba(255,255,255,0.72)" : style.theme.bg,
            border: `1px solid ${style.variant === "d" ? "rgba(255,255,255,0.92)" : style.theme.light}`,
            padding: "10px 14px",
            borderRadius: 8,
            color: palette.muted,
            fontSize: 13,
            fontWeight: 800,
            lineHeight: 1.45,
            marginBottom: 24
          }
        },
        `爬楼关键词：${card.trigger_quote}`
      ),
      h(
        "div",
        { style: { marginBottom: 24 } },
        sectionHeaderTree(style, "01", card.section1_title || "抛出探讨"),
        h(
          "div",
          { style: { borderLeft: `4px solid ${style.theme.main}`, paddingLeft: 12 } },
          h(
            "div",
            { style: { flexDirection: "row", alignItems: "center", gap: 8, marginBottom: 8 } },
            h("div", { style: { color: palette.muted, fontSize: 13, fontWeight: 800 } }, card.initiator_label),
            h(
              "div",
              { style: { background: palette.ink, color: "#ffffff", fontSize: 12, fontWeight: 800, padding: "2px 8px", borderRadius: 4 } },
              card.initiator
            )
          ),
          h("div", { style: { fontSize: 15, color: "#111827", fontWeight: 600, lineHeight: 1.45 } }, `“${card.trigger_quote}”`)
        )
      ),
      h(
        "div",
        { style: { marginBottom: 24 } },
        sectionHeaderTree(style, "02", "话题总结"),
        h(
          "div",
          {
            style: {
              background: style.textBoxFill,
              border: `1px solid ${style.textBoxStroke}`,
              padding: 14,
              borderRadius: 8,
              fontSize: 15,
              color: palette.body,
              lineHeight: 1.55
            }
          },
          card.summary
        )
      ),
      h(
        "div",
        { style: { marginBottom: 20 } },
        sectionHeaderTree(style, "03", "大家怎么说"),
        h(
          "div",
          { style: { gap: 12 } },
          ...card.points.map((point, index) =>
            h(
              "div",
              { style: { flexDirection: "row", alignItems: "flex-start", gap: 8 } },
              h("div", { style: { color: style.theme.main, fontSize: 15, fontWeight: 900, marginTop: 1 } }, String(index + 1)),
              h("div", { style: { color: palette.ink, fontSize: 15, lineHeight: 1.45, flex: 1 } }, point)
            )
          )
        )
      ),
      h(
        "div",
        { style: { flexDirection: "row", alignItems: "flex-start", marginBottom: 20 } },
        h("div", { style: { fontSize: 13, fontWeight: 800, color: palette.muted, marginRight: 8, flexShrink: 0, lineHeight: 1.6 } }, "参与者："),
        h(
          "div",
          { style: { flexDirection: "row", flexWrap: "wrap", gap: 6, flex: 1 } },
          ...participants.map((name) =>
            h(
              "div",
              {
                style: {
                  background: style.participantFill,
                  color: palette.tagText,
                  fontSize: 13,
                  fontWeight: 800,
                  padding: "2px 8px",
                  borderRadius: 4,
                  border: `1px solid ${style.participantStroke}`
                }
              },
              name
            )
          )
        )
      ),
      h(
        "div",
        { style: { background: style.highlightFill, border: `1px solid ${style.highlightStroke}`, padding: 20, borderRadius: 8 } },
        h("div", { style: { fontSize: 13, fontWeight: 900, color: style.theme.dark, marginBottom: 12 } }, card.highlight_label || "高光时刻"),
        h("div", { style: { fontSize: 17, fontWeight: 800, color: "#111827", lineHeight: 1.45, marginBottom: 12 } }, card.highlight_quote),
        h("div", { style: { fontSize: 13, fontWeight: 800, color: style.theme.dark, textAlign: "right" } }, `— ${card.highlight_speaker}`)
      )
    )
  );
}

async function writeSatoriPng(tree, width, height, file, scale = singleRenderScale, graphemeImages = {}) {
  const satori = await loadSatori();
  const fontSans = await fs.readFile("C:/Windows/Fonts/simhei.ttf");
  const svg = await satori(tree, {
    width,
    height,
    fonts: [{ name: "SimHei", data: fontSans, weight: 400, style: "normal" }],
    graphemeImages
  });
  await fs.mkdir(path.dirname(file), { recursive: true });
  let nextScale = boundedScale(width, height, scale);
  while (nextScale >= 1) {
    const png = new Resvg(svg, { fitTo: { mode: "width", value: width * nextScale }, background: "transparent" }).render().asPng();
    const dimensions = pngDimensions(png);
    const meta = { size: png.length, scale: nextScale, ...dimensions };
    if (isFeishuImageSizeOk(meta)) {
      await fs.writeFile(file, png);
      return meta;
    }
    nextScale -= 1;
  }
  throw new Error(`图片超过飞书上传限制：最大 ${feishuMaxImageDimension}x${feishuMaxImageDimension} 且不超过 10MB`);
}

async function renderSatoriImages(cards, output, layout) {
  const images = [];
  const scale = scaleForLayout(layout);
  const graphemeImages = satoriGraphemeImages(cards);
  if (layout === "collection") {
    const heights = cards.map((card) => satoriHeight(card));
    const width = cardWidth + longPadding * 2;
    const height = longPadding * 2 + heights.reduce((sum, item) => sum + item, 0) + longGap * Math.max(0, cards.length - 1);
    const tree = h(
      "div",
      {
        style: {
          width,
          height,
          background: palette.longBg,
          padding: longPadding,
          boxSizing: "border-box",
          gap: longGap,
          fontFamily: "SimHei",
          color: palette.ink
        }
      },
      ...cards.map((card) => cardTreeFor(card))
    );
    const file = path.join(output, "topic-cards-collection.png");
    const meta = await writeSatoriPng(tree, width, height, file, scale, graphemeImages);
    images.push({ path: file, width: meta.width, height: meta.height, size_bytes: meta.size, render_scale: meta.scale, engine: "satori", layout });
    return images;
  }
  for (const [index, card] of cards.entries()) {
    const height = satoriHeight(card);
    const file = path.join(output, `${card.id || `card-${index + 1}`}.png`);
    const meta = await writeSatoriPng(cardTreeFor(card), cardWidth, height, file, scale, graphemeImages);
    images.push({ path: file, width: meta.width, height: meta.height, size_bytes: meta.size, render_scale: meta.scale, engine: "satori", layout });
  }
  return images;
}

async function findTypst() {
  const candidates = [
    path.join(__dirname, "tools", "typst", "typst.exe"),
    path.join(repoRoot, "artifacts", "workplace-card-render-lab", "tools", "typst", "typst.exe"),
    path.join(
      repoRoot,
      "artifacts",
      "workplace-card-render-lab",
      "tools",
      "typst",
      "extract",
      "typst-x86_64-pc-windows-msvc",
      "typst.exe"
    )
  ];
  for (const candidate of candidates) {
    try {
      await fs.access(candidate);
      return candidate;
    } catch {
      // try next path
    }
  }
  throw new Error("未找到 typst.exe，请先安装 Typst 或放到 tools/topic-card-renderer/tools/typst/typst.exe");
}

function typstEsc(value) {
  return String(value ?? "")
    .replaceAll("\\", "\\\\")
    .replaceAll("#", "\\#")
    .replaceAll("[", "\\[")
    .replaceAll("]", "\\]");
}

function typstText(value) {
  return `[${typstEsc(value)}]`;
}

function typstRgb(value) {
  if (String(value).startsWith("rgba(")) {
    return `rgb("#ffffff")`;
  }
  return `rgb("${value}")`;
}

function typstPoints(card, style) {
  return (card.points || [])
    .slice(0, 5)
    .map(
      (point, index) => `#grid(columns: (18pt, 1fr), gutter: 8pt, align: top)[
  #text(size: 15pt, weight: "bold", fill: ${typstRgb(style.theme.main)})[${index + 1}]
][
  #text(size: 15pt, fill: rgb("#1f2937"))${typstText(point)}
]
#v(8pt)`
    )
    .join("\n");
}

function typstCardBody(card) {
  const style = styleOf(card);
  const tags = cardTags(card).join("  ");
  const rawParticipants = card.participants || [];
  const participants =
    rawParticipants.length > 14 && !rawParticipants.some((name) => String(name).startsWith("等"))
      ? `${rawParticipants.slice(0, 14).join("、")}、等`
      : rawParticipants.join("、");
  return `#block(width: ${cardWidth}pt, fill: white, stroke: 0.6pt + rgb("#e5e7eb"), radius: 12pt, clip: true)[
  #block(width: 100%, height: 6pt, fill: ${typstRgb(style.theme.main)})
  #block(width: 100%, fill: ${typstRgb(style.headerFill)}, inset: (x: 24pt, y: 20pt))[
    #text(size: 22pt, weight: "bold", fill: rgb("#111827"))${typstText(card.title)}
    #v(12pt)
    #grid(columns: (1fr, auto), align: horizon)[
      #box(fill: ${typstRgb(style.theme.light)}, radius: 4pt, inset: (x: 8pt, y: 2pt))[
        #text(size: 13pt, weight: "bold", fill: ${typstRgb(style.theme.dark)})${typstText(tags)}
      ]
    ][
      #text(size: 13pt, fill: rgb("#6b7280"))${typstText(card.time_range)}
    ]
  ]
  #line(length: 100%, stroke: 0.5pt + rgb("#f3f4f6"))
  #block(width: 100%, fill: ${typstRgb(style.bodyFill)}, inset: (x: 24pt, y: 20pt))[
    #text(size: 16pt, weight: "bold", fill: ${typstRgb(style.theme.main)})[01]
    #h(6pt)
    #text(size: 15pt, weight: "bold")${typstText(card.section1_title || "谁引起的")}
    #v(10pt)
    #grid(columns: (4pt, 1fr), gutter: 8pt)[
      #block(width: 4pt, height: 66pt, fill: ${typstRgb(style.theme.main)})[]
    ][
      #text(size: 12pt, weight: "bold", fill: rgb("#6b7280"))${typstText(card.initiator_label)}
      #h(8pt)
      #box(fill: rgb("#1f2937"), radius: 4pt, inset: (x: 8pt, y: 2pt))[
        #text(size: 11pt, weight: "bold", fill: white)${typstText(card.initiator)}
      ]
      #v(8pt)
      #text(size: 13pt, fill: rgb("#111827"))${typstText(`“${card.trigger_quote}”`)}
    ]

    #v(22pt)
    #text(size: 15pt, weight: "bold", fill: ${typstRgb(style.theme.main)})[02]
    #h(6pt)
    #text(size: 15pt, weight: "bold")[话题总结]
    #v(10pt)
    #block(width: 100%, fill: ${typstRgb(style.textBoxFill)}, stroke: 0.6pt + rgb("#f3f4f6"), radius: 8pt, inset: 14pt)[
      #text(size: 13pt, fill: rgb("#374151"))${typstText(card.summary)}
    ]

    #v(22pt)
    #text(size: 15pt, weight: "bold", fill: ${typstRgb(style.theme.main)})[03]
    #h(6pt)
    #text(size: 15pt, weight: "bold")[大家怎么说]
    #v(10pt)
    ${typstPoints(card, style)}

    #v(8pt)
    #block(width: 100%, fill: ${typstRgb(style.participantFill)}, radius: 8pt, inset: 12pt)[
      #text(size: 12pt, weight: "bold", fill: rgb("#6b7280"))[参与者：]
      #h(4pt)
      #text(size: 12pt, fill: rgb("#374151"))${typstText(participants)}
    ]

    #v(18pt)
    #block(width: 100%, fill: ${typstRgb(style.highlightFill)}, stroke: 0.8pt + ${typstRgb(style.highlightStroke)}, radius: 8pt, inset: 18pt)[
      #text(size: 12pt, weight: "bold", fill: ${typstRgb(style.theme.dark)})${typstText(card.highlight_label || "高光时刻")}
      #v(10pt)
      #text(size: 15pt, weight: "bold", fill: rgb("#111827"))${typstText(card.highlight_quote)}
      #v(8pt)
      #align(right)[#text(size: 12pt, weight: "bold", fill: ${typstRgb(style.theme.dark)})${typstText(`— ${card.highlight_speaker}`)}]
    ]
  ]
]`;
}

function typstDocument(cards, layout) {
  if (layout === "collection") {
    const pageWidth = cardWidth + longPadding * 2;
    return `#set page(width: ${pageWidth}pt, height: auto, margin: 0pt, fill: ${typstRgb(palette.longBg)})
#set text(font: ("Microsoft YaHei", "Segoe UI Emoji"), lang: "zh", fill: rgb("#1f2937"))
#set par(leading: 0.55em)

#block(width: 100%, inset: ${longPadding}pt)[
${cards.map((card) => typstCardBody(card)).join(`\n#v(${longGap}pt)\n`)}
]`;
  }
  return `#set page(width: ${cardWidth}pt, height: auto, margin: 0pt, fill: white)
#set text(font: ("Microsoft YaHei", "Segoe UI Emoji"), lang: "zh", fill: rgb("#1f2937"))
#set par(leading: 0.55em)

${typstCardBody(cards[0])}`;
}

function pngDimensions(buffer) {
  if (buffer.length < 24 || buffer.toString("ascii", 1, 4) !== "PNG") {
    return { width: 0, height: 0 };
  }
  return { width: buffer.readUInt32BE(16), height: buffer.readUInt32BE(20) };
}

async function compileTypst(typstPath, source, file, scale = singleRenderScale) {
  await fs.mkdir(path.dirname(source), { recursive: true });
  await fs.mkdir(path.dirname(file), { recursive: true });
  let nextScale = scale;
  while (nextScale >= 1) {
    await execFileAsync(typstPath, ["compile", "--ppi", String(72 * nextScale), source, file], { windowsHide: true });
    const png = await fs.readFile(file);
    const meta = { size: png.length, scale: nextScale, ...pngDimensions(png) };
    if (isFeishuImageSizeOk(meta)) {
      return meta;
    }
    nextScale -= 1;
  }
  throw new Error(`图片超过飞书上传限制：最大 ${feishuMaxImageDimension}x${feishuMaxImageDimension} 且不超过 10MB`);
}

async function renderTypstImages(cards, output, layout) {
  const typstPath = await findTypst();
  const images = [];
  const scale = scaleForLayout(layout);
  if (layout === "collection") {
    const source = path.join(output, "topic-cards-collection.typ");
    const file = path.join(output, "topic-cards-collection.png");
    await fs.writeFile(source, typstDocument(cards, "collection"), "utf8");
    const meta = await compileTypst(typstPath, source, file, scale);
    images.push({ path: file, width: meta.width, height: meta.height, size_bytes: meta.size, render_scale: meta.scale, engine: "typst", layout });
    return images;
  }
  for (const [index, card] of cards.entries()) {
    const name = card.id || `card-${index + 1}`;
    const source = path.join(output, `${name}.typ`);
    const file = path.join(output, `${name}.png`);
    await fs.writeFile(source, typstDocument([card], "single"), "utf8");
    const meta = await compileTypst(typstPath, source, file, scale);
    images.push({ path: file, width: meta.width, height: meta.height, size_bytes: meta.size, render_scale: meta.scale, engine: "typst", layout });
  }
  return images;
}

async function main() {
  const input = arg("input");
  const output = arg("output");
  const engine = arg("engine", "satori");
  const layout = arg("layout", "single");
  if (!input || !output) throw new Error("missing --input or --output");
  const payload = JSON.parse(await fs.readFile(input, "utf8"));
  const cards = payload.cards || [];
  await fs.mkdir(output, { recursive: true });
  if (engine === "satori") {
    await preloadEmojiAssets(cards);
    const images = await renderSatoriImages(cards, output, layout);
    process.stdout.write(JSON.stringify({ images }, null, 2));
    return;
  }
  if (engine === "typst") {
    const images = await renderTypstImages(cards, output, layout);
    process.stdout.write(JSON.stringify({ images }, null, 2));
    return;
  }
  await preloadEmojiAssets(cards);
  const images = [];
  const scale = scaleForLayout(layout);
  if (layout === "collection") {
    let y = longPadding;
    let body = "";
    for (const card of cards) {
      const rendered = cardSvg(card, longPadding, y);
      body += rendered.svg;
      y += rendered.height + longGap;
    }
    const width = cardWidth + longPadding * 2;
    const height = y - longGap + longPadding;
    const file = path.join(output, "topic-cards-collection.png");
    const meta = await writePng(rootSvg(width, height, body, palette.longBg), file, scale);
    images.push({ path: file, width: meta.width, height: meta.height, size_bytes: meta.size, render_scale: meta.scale, engine, layout });
  } else {
    for (const [index, card] of cards.entries()) {
      const rendered = cardSvg(card);
      const file = path.join(output, `${card.id || `card-${index + 1}`}.png`);
      const meta = await writePng(rootSvg(cardWidth, rendered.height, rendered.svg), file, scale);
      images.push({ path: file, width: meta.width, height: meta.height, size_bytes: meta.size, render_scale: meta.scale, engine, layout });
    }
  }
  process.stdout.write(JSON.stringify({ images }, null, 2));
}

main().catch((error) => {
  process.stderr.write(error?.stack || String(error));
  process.exit(1);
});
