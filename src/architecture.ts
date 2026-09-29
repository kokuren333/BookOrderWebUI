// Intent-driven publication architecture: WebUI model.
//
// The vocabulary (structure modes, archetypes, block library, visual taxonomy, source roles, authority, asset roles,
// citation options, intent signals) is job-template/schemas/publication-architecture.json — the same file the job's
// Python scripts read (publication_architecture.py, source_roles.py, bibliography.py). Nothing here is a second list.
//
// What the WebUI writes to project.json:
//   publication_architecture   mode (auto | guided | fixed), archetype, block / exercise / visual / evidence policy, notes
//   citations                  in-text style separate from bibliography style, numbering, grouping and roles
//   input.sources[].usage      per-file role metadata for content files (evidence, background, …)
//   input.assets[]             files that are not content (layout / style / visual references, figures, logos …)
// A job without `publication_architecture` is a legacy job and runs in FIXED mode (job-template docs).
import vocab from '../job-template/schemas/publication-architecture.json' with { type: 'json' };

export const VOCAB = vocab;
export type StructureMode = 'auto' | 'guided' | 'fixed';
export type UiMode = 'quick' | 'advanced';
export type BlockState = 'preferred' | 'discouraged' | 'forbidden';
export const STRUCTURE_MODES = vocab.structure_modes as Record<StructureMode, { label: string; description: string; description_ja: string }>;
export const ARCHETYPES = vocab.archetypes as Record<string, { label: string; en: string; reading_mode: string; preferred_blocks: string[]; discouraged_blocks: string[]; exercise_policy: string; visual_density: string }>;
export const BLOCKS = vocab.blocks as Record<string, { label: string; alias_of?: string; visual?: boolean; positions: string[] }>;
export const BLOCK_IDS = Object.keys(BLOCKS).filter(id => !BLOCKS[id].alias_of);
export const VISUAL_TYPES = vocab.visual_types as Record<string, { label: string; device: string }>;
export const EXERCISE_POLICIES = vocab.exercise_policies as Record<string, string>;
export const VISUAL_DENSITIES = Object.keys(vocab.visual_densities);
export const SOURCE_ROLES = vocab.source_roles as Record<string, { label: string; content: boolean; citation_allowed: boolean; group: string | null; description: string; description_ja: string }>;
export const AUTHORITY = vocab.source_authority as Record<string, { label: string; rank: number | null }>;
export const ASSET_ROLES = vocab.asset_roles as Record<string, { label: string; source_role: string }>;
export const QUICK_USES = vocab.quick_uses as Record<string, { label: string; role: string; asset_role?: string }>;
export const CITATIONS = vocab.citations;

export interface ArchitectureOptions {
  mode: StructureMode;
  archetype: string;            // 'auto' or an archetype id
  secondaryArchetype: string;   // '' or an archetype id
  archetypeNote: string;        // free text next to the enum (「看護師向けの実務書だが入門教科書の要素も」)
  blocks: Record<string, BlockState>;   // only explicit choices; unlisted blocks follow the archetype
  exercisePolicy: string;       // 'auto' or an exercise policy
  visualDensity: string;        // 'auto' or a density
  visualPreferred: string[]; visualAvoid: string[];
  chapterArchitecture: string;  // free text: how chapters should differ
  evidencePriority: string;     // 'auto' | low | medium | high | strict
  preferredAuthority: string[]; evidenceNote: string;
  layoutStrategy: string; tone: string;
}
export const defaultArchitecture: ArchitectureOptions = {
  mode: vocab.default_mode as StructureMode, archetype: 'auto', secondaryArchetype: '', archetypeNote: '', blocks: {},
  exercisePolicy: 'auto', visualDensity: 'auto', visualPreferred: [], visualAvoid: [], chapterArchitecture: '',
  evidencePriority: 'auto', preferredAuthority: [], evidenceNote: '', layoutStrategy: '', tone: '',
};

export interface CitationOptions {
  inText: 'numeric' | 'author-year' | 'note';
  footnoteStyle: 'full' | 'short' | 'numbered_reference';
  bibliographyStyle: 'auto' | 'standard' | 'author_date';
  numbering: 'numbered' | 'unnumbered';
  scope: 'per_group' | 'continuous';
  sort: 'auto' | 'citation_order' | 'author' | 'title';
  groups: { cited: boolean; background: boolean; visual: boolean; design: boolean };
}
export const defaultCitation: Omit<CitationOptions, 'inText'> = {
  footnoteStyle: 'full', bibliographyStyle: 'auto', numbering: 'numbered', scope: 'per_group', sort: 'auto',
  groups: { cited: true, background: true, visual: true, design: false },
};

export interface FileUsage {
  label: string; role: string; assetRole: string;       // assetRole '' = not an asset
  authority: string; citationAllowed: 'auto' | 'yes' | 'no';
  intendedUsage: string; intendedChapter: string; intendedSection: string; priority: 'low' | 'normal' | 'high';
  caption: string; cropAllowed: boolean; redrawAllowed: boolean; transformAllowed: boolean; useVerbatim: boolean;
  notes: string; roleOrigin: 'user' | 'inferred';
}

const IMAGE = /\.(png|jpe?g|gif|webp|svg|tiff?|bmp|heic)$/i;
/** Quick-mode role estimate from the file name and type. Shown as 「推定」 and editable; the agent refines unset roles. */
export function inferUsage(name: string, type = ''): FileUsage {
  const lower = name.normalize('NFKC').toLowerCase();
  const image = IMAGE.test(lower) || type.startsWith('image/');
  const has = (re: RegExp) => re.test(lower);
  let role = 'evidence'; let assetRole = ''; let authority = 'unknown';
  if (has(/layout|レイアウト|組版|誌面|紙面|誌面見本|page ?sample|見本/)) { role = 'layout_reference'; assetRole = 'layout_reference'; }
  else if (has(/style|文体|トーン|雰囲気|mood|moodboard|デザイン参考|配色/)) { role = image ? 'visual_reference' : 'style_reference'; assetRole = role; }
  else if (has(/logo|ロゴ/)) { role = 'asset'; assetRole = 'logo'; }
  else if (has(/cover|表紙/)) { role = 'asset'; assetRole = 'cover_candidate'; }
  else if (has(/扉|opener/)) { role = 'asset'; assetRole = 'chapter_opener'; }
  else if (image) { role = 'asset'; assetRole = 'inline_figure'; }
  else if (has(/blog|ブログ|note\.com|note_|体験|経験談|コラム|エッセイ|感想|現場の声/)) { role = 'background'; authority = has(/体験|感想/) ? 'anecdotal' : 'professional_experience'; }
  if (role === 'evidence') {
    if (has(/guideline|ガイドライン|指針|診療/)) authority = 'guideline';
    else if (has(/厚生労働省|mhlw|省|庁|government|政府|自治体/)) authority = 'governmental';
    else if (has(/journal|論文|doi|pubmed|jama|nejm|lancet/)) authority = 'peer_reviewed';
    else if (has(/学会|society|association|協会/)) authority = 'institutional';
  }
  return { label: name, role, assetRole, authority, citationAllowed: 'auto', intendedUsage: '', intendedChapter: '', intendedSection: '', priority: 'normal',
    caption: '', cropAllowed: true, redrawAllowed: role === 'redraw_source' || role === 'visual_reference', transformAllowed: true, useVerbatim: assetRole === 'inline_figure' || assetRole === 'logo',
    notes: '', roleOrigin: 'inferred' };
}
/** Roles a URL can take (a web page is never a placed asset or a redraw file). */
export const URL_ROLES = ['evidence', 'background', 'further_reading', 'structure_reference', 'layout_reference', 'visual_reference'] as const;
/** URL role estimate from the address alone (the WebUI never fetches pages; the agent refines unset roles after reading). */
export function inferUrlUsage(url: string, title = ''): FileUsage {
  let host = ''; let path = '';
  try { const u = new URL(url); host = u.hostname.toLowerCase(); path = decodeURIComponent(u.pathname + u.search).toLowerCase(); } catch { path = url.toLowerCase(); }
  const text = `${host} ${path} ${title}`.normalize('NFKC').toLowerCase();
  const has = (re: RegExp) => re.test(text);
  let role = 'evidence'; let authority = 'unknown';
  if (has(/layout|レイアウト|組版|誌面|紙面|template|テンプレート|page-?sample|見本|behance|dribbble|pinterest/)) role = has(/behance|dribbble|pinterest|illustration|図解|infographic/) ? 'visual_reference' : 'layout_reference';
  else if (has(/図解|infographic|illustration/)) role = 'visual_reference';
  else if (has(/(^|\.)note\.com|hatenablog|ameblo|livedoor|blog|ブログ|medium\.com|qiita|zenn\.dev|体験|経験談|感想|コラム|column|essay/)) {
    role = 'background'; authority = has(/体験|感想/) ? 'anecdotal' : 'professional_experience';
  }
  if (role === 'evidence') {
    if (has(/guideline|ガイドライン|指針|minds\.jcqhc/)) authority = 'guideline';
    else if (has(/pubmed|ncbi\.nlm|doi\.org|jstage|cinii|nature\.com|sciencedirect|springer|wiley|nejm|jamanetwork|thelancet|bmj\.com|arxiv/)) authority = has(/arxiv/) ? 'expert_commentary' : 'peer_reviewed';
    else if (has(/\.go\.jp|\.gov(\.|$|\/)|\.gov\b|\.lg\.jp|mhlw|who\.int|europa\.eu/)) authority = 'governmental';
    else if (has(/\.or\.jp|\.ac\.jp|\.edu(\/|$)|gakkai|society|association|学会|協会/)) authority = 'institutional';
    else if (has(/wikipedia|matome|まとめ/)) { role = 'background'; authority = 'unknown'; }
  }
  return { ...inferUsage(url), label: title || url, role, assetRole: '', authority, redrawAllowed: false, useVerbatim: false, roleOrigin: 'inferred' };
}
/** Bulk edit: apply the same fields to several usages (each becomes a user choice). */
export function applyBulk<K extends string>(usages: Record<K, FileUsage>, keys: K[], patch: Partial<FileUsage>): Record<K, FileUsage> {
  const out = { ...usages };
  for (const key of keys) if (out[key]) out[key] = { ...out[key], ...patch, roleOrigin: 'user' };
  return out;
}
export const isContent = (usage: FileUsage) => Boolean(SOURCE_ROLES[usage.role]?.content);
export const isImage = (name: string) => IMAGE.test(name);

/** Apply a quick-use toggle (内容資料 / レイアウト参考 / 図解の参考 / 素材 / 再作図) to a file's usage. */
export function applyQuickUse(usage: FileUsage, use: string): FileUsage {
  const spec = QUICK_USES[use];
  return { ...usage, role: spec.role, assetRole: spec.asset_role ?? '', redrawAllowed: use === 'redraw' ? true : usage.redrawAllowed,
    useVerbatim: use === 'redraw' ? false : usage.useVerbatim, roleOrigin: 'user' };
}
export function quickUseOf(usage: FileUsage): string {
  if (usage.role === 'redraw_source') return 'redraw';
  if (usage.role === 'layout_reference') return 'use_as_layout_reference';
  if (usage.role === 'visual_reference' || usage.role === 'style_reference') return 'use_as_visual_reference';
  if (usage.role === 'asset') return 'use_as_asset';
  return 'use_as_content';
}

/** project.json `usage` for one file (only meaningful values; the role is always written). */
export function usagePayload(u: FileUsage) {
  const out: Record<string, unknown> = { role: u.role, role_origin: u.roleOrigin };
  if (u.label.trim()) out.label = u.label.trim();
  if (u.assetRole) out.asset_role = u.assetRole;
  if (u.authority && u.authority !== 'unknown') out.authority = u.authority;
  if (u.citationAllowed !== 'auto') out.citation_allowed = u.citationAllowed === 'yes';
  for (const [key, value] of [['intended_usage', u.intendedUsage], ['intended_chapter', u.intendedChapter], ['intended_section', u.intendedSection], ['caption', u.caption], ['notes', u.notes]] as const)
    if (value.trim()) out[key] = value;
  if (u.priority !== 'normal') out.priority = u.priority;
  if (u.assetRole) Object.assign(out, { crop_allowed: u.cropAllowed, redraw_allowed: u.redrawAllowed, transform_allowed: u.transformAllowed, use_verbatim: u.useVerbatim });
  return out;
}

/** project.json `publication_architecture`: the mode always, everything else only when chosen. */
export function architecturePayload(a: ArchitectureOptions) {
  const out: Record<string, unknown> = { mode: a.mode };
  if (a.archetype !== 'auto') out.archetype = a.archetype;
  if (a.secondaryArchetype) out.secondary_archetype = a.secondaryArchetype;
  const lists: Record<BlockState, string[]> = { preferred: [], discouraged: [], forbidden: [] };
  for (const [block, state] of Object.entries(a.blocks)) lists[state].push(block);
  const policy = Object.fromEntries(Object.entries(lists).filter(([, v]) => v.length));
  if (Object.keys(policy).length) out.block_policy = policy;
  if (a.exercisePolicy !== 'auto') out.exercise_policy = a.exercisePolicy;
  const visual: Record<string, unknown> = {};
  if (a.visualDensity !== 'auto') visual.density = a.visualDensity;
  if (a.visualPreferred.length) visual.preferred_types = a.visualPreferred;
  if (a.visualAvoid.length) visual.avoid_types = a.visualAvoid;
  if (Object.keys(visual).length) out.visual_policy = visual;
  const evidence: Record<string, unknown> = {};
  if (a.evidencePriority !== 'auto') evidence.priority = a.evidencePriority;
  if (a.preferredAuthority.length) evidence.preferred_authority = a.preferredAuthority;
  if (a.evidenceNote.trim()) evidence.note = a.evidenceNote;
  if (Object.keys(evidence).length) out.evidence_policy = evidence;
  for (const [key, value] of [['archetype_note', a.archetypeNote], ['chapter_architecture', a.chapterArchitecture], ['layout_strategy', a.layoutStrategy], ['tone', a.tone]] as const)
    if (value.trim()) out[key] = value;
  return out;
}

/** project.json `citations`: in-text form and back matter as separate settings (legacy `style` kept). */
export function citationPayload(inText: CitationOptions['inText'], c: Omit<CitationOptions, 'inText'>) {
  return {
    style: inText, in_text_citation_style: inText,
    ...(inText === 'note' ? { footnote_style: c.footnoteStyle } : {}),
    bibliography_style: c.bibliographyStyle === 'auto' ? (inText === 'author-year' ? 'author_date' : 'standard') : c.bibliographyStyle,
    bibliography_numbering: c.numbering, numbering_scope: c.scope,
    ...(c.sort !== 'auto' ? { bibliography_sort: c.sort } : {}),
    bibliography_grouping: { ...c.groups },
  };
}

/** Explicit wishes BookOrder will read from the user's words (same patterns as the job's Intent Interpreter). */
export function detectSignals(text: string): { id: string; quote: string; effect: Record<string, unknown> }[] {
  const found = [];
  const normalized = text.normalize('NFKC');
  for (const signal of vocab.intent_signals) {
    for (const pattern of signal.patterns) {
      const match = new RegExp(pattern, 'i').exec(normalized);
      if (match) { found.push({ id: signal.id, quote: match[0], effect: signal.effect as Record<string, unknown> }); break; }
    }
  }
  return found;
}
export function signalText(effect: Record<string, unknown>): string {
  const parts: string[] = [];
  const names = (list: unknown) => (list as string[]).map(b => BLOCKS[b]?.label ?? b).join('・');
  if (effect.forbid) parts.push(`${names(effect.forbid)}を入れない`);
  if (effect.prefer) parts.push(`${names(effect.prefer)}を重視`);
  if (effect.discourage) parts.push(`${names(effect.discourage)}を控える`);
  if (effect.visual_density) parts.push(`図表密度 ${effect.visual_density}`);
  if (effect.tone) parts.push(`語り口: ${effect.tone}`);
  if (effect.archetype) parts.push(`出版物タイプの手がかり: ${ARCHETYPES[effect.archetype as string]?.label}`);
  if (effect.exercise_policy && !effect.forbid) parts.push(`問題: ${effect.exercise_policy}`);
  if (effect.evidence_priority) parts.push(`根拠重視 ${effect.evidence_priority}`);
  return parts.join(' / ');
}
